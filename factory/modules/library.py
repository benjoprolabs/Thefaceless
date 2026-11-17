"""Module 5: Voice & Visual Library. Reusable narrator presets and visual styles."""

from factory.core.config import FactoryError
from factory.core.options import add_division, add_language


def voice_presets(ctx, language=None):
    presets = ctx.config.voice_presets
    return {k: v for k, v in presets.items() if not language or language in v["languages"]}


def get_preset(ctx, preset_id):
    presets = ctx.config.voice_presets
    if preset_id not in presets:
        raise FactoryError(f"Unknown voice preset '{preset_id}'. See: python -m factory library voices")
    return presets[preset_id]


def cmd_voices(args, ctx):
    from factory.voice_studio.clones import list_clones  # local import avoids a cycle

    print(f"{'PRESET':<22} {'LANGS':<7} DESCRIPTION")
    for pid, p in voice_presets(ctx, args.lang).items():
        print(f"{pid:<22} {','.join(p['languages']):<7} {p['description']}")
    ready = [c for c in list_clones(ctx) if c["status"] == "ready"]
    if ready:
        print("\nPersonal clones (use as clone:<name>):")
        for c in ready:
            print(f"  clone:{c['name']:<16} owner: {c['owner']}")
    return 0


def cmd_visuals(args, ctx):
    divisions = ctx.config.divisions
    for div_id, div in divisions.items():
        if args.division and div_id != args.division:
            continue
        style = ctx.config.visual_styles[div["visual_style"]]
        print(f"{div['name']} → {div['visual_style']}")
        print(f"    look   : {style['description']}")
        print(f"    music  : {style['music_mood']}")
        print(f"    captions: {style['caption_style']}")
    return 0


def register(sub):
    p = sub.add_parser("library", help="Voice & Visual Library: presets and styles")
    s = p.add_subparsers(metavar="action", required=True)
    v = s.add_parser("voices", help="narrator voice presets and personal clones")
    add_language(v)
    v.set_defaults(func=cmd_voices)
    vs = s.add_parser("visuals", help="visual styles per division")
    add_division(vs)
    vs.set_defaults(func=cmd_visuals)
