"""`python -m factory voice ...`: command-line front end for Voice Studio."""

import json

from factory.core.config import FactoryError
from factory.core.projects import find_project
from factory.modules.library import cmd_voices
from factory.voice_studio import audio, clones, service
from factory.voice_studio.engines import ENGINES, get_engine
from factory.voice_studio.engines.elevenlabs import ElevenLabsEngine


def make_confirm(args):
    """--yes skips the prompt; otherwise ask on the terminal (default: No)."""
    def confirm(message):
        if getattr(args, "yes", False):
            print(f"{message} → confirmed with --yes")
            return True
        try:
            answer = input(f"{message} [y/N] ").strip().lower()
        except EOFError:  # no interactive terminal: treat as "No"
            return False
        return answer in ("y", "yes")
    return confirm


def show_item(item, prefix="Saved"):
    dur = f"{item['duration_sec']:.1f}s" if item.get("duration_sec") else "?s"
    print(f"{prefix} {item['id']} [{item['kind']}] {item['file']} ({dur})")


def cmd_engines(args, ctx):
    default = ctx.config.voice_studio["default_engine"]
    for name in ENGINES:
        engine = get_engine(ctx, name)
        flags = []
        if name == default:
            flags.append("default")
        if engine.sends_data_externally:
            flags.append("sends data externally, asks first")
        if isinstance(engine, ElevenLabsEngine):
            flags.append(f"API key {'found' if engine.api_key_present() else 'not set'} (${engine.key_env})")
            flags.append("calls disabled in Phase 1")
        print(f"{name:<11} {engine.describe()}\n            [{'; '.join(flags)}]")
    return 0


def cmd_import(args, ctx):
    p = find_project(ctx, args.project)
    show_item(service.import_audio(ctx, p, args.file, args.note), "Imported")
    return 0


def cmd_record(args, ctx):
    p = find_project(ctx, args.project)
    print(f"Recording {args.seconds}s from the microphone...")
    show_item(service.record_take(ctx, p, args.seconds, args.note), "Recorded")
    return 0


def cmd_list(args, ctx):
    if args.project:
        p = find_project(ctx, args.project)
        rows = [(p, i, service.audio_log(ctx, p).path_of(i).exists()) for i in service.audio_log(ctx, p).items]
        selected = service.audio_log(ctx, p).data["selected"]
    else:
        rows, selected = service.history(ctx), None
    if not rows:
        print("No audio yet.")
    for p, item, exists in rows:
        mark = "*" if item["id"] == selected else " "
        extra = item.get("voice") or item.get("source_file") or ""
        parent = f"← {item['parent']}" if item.get("parent") else ""
        missing = "" if exists else "  (file not on this computer)"
        project = "" if args.project else f"{p.id}  "
        print(f"{mark}{project}{item['id']} {item['kind']:<9} {item['created']} {extra:<22} {parent:<7}{missing}")
    if selected:
        print("* = selected take")
    return 0


def cmd_play(args, ctx):
    p = find_project(ctx, args.project)
    log = service.audio_log(ctx, p)
    path = log.path_of(log.get(args.audio_id))
    print(f"Playing {path.name}")
    audio.play(path)
    return 0


def cmd_trim(args, ctx):
    p = find_project(ctx, args.project)
    show_item(service.trim_audio(ctx, p, args.audio_id, args.start, args.end), "Trimmed →")
    return 0


def cmd_select(args, ctx):
    p = find_project(ctx, args.project)
    item = service.select(ctx, p, args.audio_id)
    print(f"Selected {item['id']} ({item['file']}) as the take for {p.id}")
    return 0


def cmd_tts(args, ctx):
    p = find_project(ctx, args.project)
    text = open(args.text_file, encoding="utf-8").read() if args.text_file else None
    if args.dry_run:
        return dry_run(ctx, p, args, "tts", text)
    show_item(service.text_to_speech(ctx, p, args.voice, args.engine, text, make_confirm(args)))
    return 0


def cmd_convert(args, ctx):
    p = find_project(ctx, args.project)
    if args.dry_run:
        return dry_run(ctx, p, args, "convert")
    show_item(service.convert_voice(ctx, p, args.audio_id, args.voice, args.engine, make_confirm(args)))
    return 0


def dry_run(ctx, project, args, action, text=None):
    """Show what would be sent, without sending anything."""
    from factory.modules.scripts import project_narration
    engine = get_engine(ctx, args.engine)
    voice = args.voice or project.meta["voice_preset"]
    voice_id, settings = service.resolve_voice(ctx, voice, engine, project.language, allow_missing=True)
    if not hasattr(engine, "build_tts_request"):
        print(f"Engine '{engine.name}' runs locally; nothing would be sent anywhere.")
        return 0
    if action == "tts":
        text = text or project_narration(ctx, project)
        req = engine.build_tts_request(text, voice_id, project.language, settings)
        req["json"]["text"] = req["json"]["text"][:80] + ("..." if len(text) > 80 else "")
    else:
        log = service.audio_log(ctx, project)
        req = engine.build_sts_request(log.path_of(log.get(args.audio_id)), voice_id, settings)
    print("DRY RUN: nothing sent. Request that would be made:")
    print(json.dumps(req, indent=2, ensure_ascii=False))
    return 0


def cmd_export(args, ctx):
    p = find_project(ctx, args.project)
    show_item(service.export_audio(ctx, p, args.audio_id, args.format), "Exported")
    return 0


# ---- clones

def cmd_clone_init(args, ctx):
    data = clones.init_clone(ctx, args.name, args.owner)
    folder = clones.clone_dir(ctx, data["name"]).relative_to(ctx.paths.root)
    print(f"Created {folder}/")
    print(f"1. Open {folder}/consent.md, tick every box and sign with: {data['owner']}")
    print(f"2. Record yourself reading: \"{data['verification_phrase']}\"")
    print(f"3. python -m factory voice clone verify {data['name']} <that-recording>")
    print(f"4. python -m factory voice clone add-sample {data['name']} <clean 1–3 min recording>")
    print(f"5. python -m factory voice clone create {data['name']} --engine mock")
    return 0


def cmd_clone_sample(args, ctx):
    dest = clones.add_sample(ctx, args.name, args.file)
    print(f"Added sample {dest.name}")
    return 0


def cmd_clone_verify(args, ctx):
    data = clones.verify_clone(ctx, args.name, args.recording)
    print(f"Verified '{data['name']}' for owner {data['owner']}. "
          "(Phrase recording kept for manual review.)")
    return 0


def cmd_clone_create(args, ctx):
    data = clones.create_clone(ctx, args.name, get_engine(ctx, args.engine), make_confirm(args))
    print(f"Clone '{data['name']}' ready. Use it with --voice clone:{data['name']}")
    return 0


def cmd_clone_list(args, ctx):
    rows = clones.list_clones(ctx)
    if not rows:
        print("No personal voice clones.")
    for c in rows:
        engines = ", ".join(c["engine_voice_ids"]) or "-"
        print(f"{c['name']:<20} {c['status']:<17} owner: {c['owner']:<20} samples: {len(c['samples'])}  engines: {engines}")
    return 0


def cmd_clone_delete(args, ctx):
    if not make_confirm(args)(f"Permanently delete local clone '{args.name}' and its samples?"):
        raise FactoryError("Cancelled.")
    data = clones.delete_clone(ctx, args.name)
    print(f"Deleted local clone '{data['name']}'.")
    remote = [e for e in data["engine_voice_ids"] if get_engine(ctx, e).sends_data_externally]
    if remote:
        print(f"Also delete it in your {', '.join(remote)} account.")
    return 0


def register(sub):
    v = sub.add_parser("voice", help="Voice Studio: record, TTS, voice changer, clones, audio")
    s = v.add_subparsers(metavar="action", required=True)

    def project_cmd(name, func, help_text):
        p = s.add_parser(name, help=help_text)
        p.add_argument("project")
        p.set_defaults(func=func)
        return p

    def engine_opts(p):
        p.add_argument("--engine", help="mock (default) or elevenlabs")
        p.add_argument("--yes", action="store_true", help="confirm sending data to an external engine")
        p.add_argument("--dry-run", action="store_true", help="show the request without sending")

    s.add_parser("engines", help="available voice engines").set_defaults(func=cmd_engines)
    pr = s.add_parser("presets", help="narrator voice presets")
    pr.add_argument("--lang")
    pr.set_defaults(func=cmd_voices)

    p = project_cmd("import", cmd_import, "add an MP3/WAV/M4A recording as a new take")
    p.add_argument("file")
    p.add_argument("--note", default="")
    p = project_cmd("record", cmd_record, "record a new take from the microphone")
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--note", default="")

    lp = s.add_parser("list", help="audio history (one project, or all)")
    lp.add_argument("project", nargs="?")
    lp.set_defaults(func=cmd_list)

    p = project_cmd("play", cmd_play, "play an audio file")
    p.add_argument("audio_id")
    p = project_cmd("trim", cmd_trim, "trim a take into edited/ (original kept)")
    p.add_argument("audio_id")
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float)
    p = project_cmd("select", cmd_select, "choose the final take")
    p.add_argument("audio_id")

    p = project_cmd("tts", cmd_tts, "text-to-speech from the project script")
    p.add_argument("--voice", help="preset id or clone:<name> (default: project preset)")
    p.add_argument("--text-file", help="use this text instead of the script")
    engine_opts(p)
    p = project_cmd("convert", cmd_convert, "AI voice changer: re-voice a recording")
    p.add_argument("audio_id")
    p.add_argument("--voice", required=True, help="preset id or clone:<name>")
    engine_opts(p)

    p = project_cmd("export", cmd_export, "export MP3/WAV to exports/")
    p.add_argument("audio_id", nargs="?", help="default: selected take")
    p.add_argument("--format", default="wav", choices=["wav", "mp3"])

    c = s.add_parser("clone", help="personal voice cloning (your own voice only)")
    cs = c.add_subparsers(metavar="step", required=True)
    x = cs.add_parser("init", help="start a clone and create the consent form")
    x.add_argument("name")
    x.add_argument("--owner", required=True, help="your full name")
    x.set_defaults(func=cmd_clone_init)
    x = cs.add_parser("verify", help="check signed consent + phrase recording")
    x.add_argument("name")
    x.add_argument("recording")
    x.set_defaults(func=cmd_clone_verify)
    x = cs.add_parser("add-sample", help="add a voice sample")
    x.add_argument("name")
    x.add_argument("file")
    x.set_defaults(func=cmd_clone_sample)
    x = cs.add_parser("create", help="create the clone on an engine")
    x.add_argument("name")
    x.add_argument("--engine")
    x.add_argument("--yes", action="store_true")
    x.set_defaults(func=cmd_clone_create)
    cs.add_parser("list", help="list clones").set_defaults(func=cmd_clone_list)
    x = cs.add_parser("delete", help="delete a clone and its samples")
    x.add_argument("name")
    x.add_argument("--yes", action="store_true")
    x.set_defaults(func=cmd_clone_delete)
