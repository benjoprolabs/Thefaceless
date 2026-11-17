"""Voice Studio workflows. Pure Python functions: the CLI calls them today and a
future web UI can call the same functions.

`confirm` is a callable(message) -> bool. It is called before anything is sent
to an engine that sends data off this computer. Return False to cancel.
"""

import os
import stat
import shutil
from pathlib import Path

from factory.core.config import FactoryError
from factory.core.files import sha256
from factory.core.projects import iter_projects
from factory.modules.library import get_preset
from factory.modules.scripts import project_narration
from factory.voice_studio import audio, clones
from factory.voice_studio.audio_log import AudioLog
from factory.voice_studio.engines import get_engine


def voice_dir(ctx, project):
    return project.stage_dir(ctx, "voice")


def audio_log(ctx, project):
    return AudioLog(voice_dir(ctx, project))


def _protect(path):
    """Make an original recording read-only so it is never edited by accident."""
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass


def _unique(path):
    n = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    return candidate


# ------------------------------------------------------------ raw audio

def import_audio(ctx, project, file, note=""):
    src = Path(file)
    allowed = ctx.config.voice_studio["import_formats"]
    if not src.is_file():
        raise FactoryError(f"File not found: {file}")
    if audio.ext(src) not in allowed:
        raise FactoryError(f"Unsupported format .{audio.ext(src)}. Use: {', '.join(allowed)}")
    log = audio_log(ctx, project)
    take = log.next_take()
    dest = _unique(voice_dir(ctx, project) / "raw" / f"take-{take:03d}_{src.name}")
    shutil.copy2(src, dest)
    _protect(dest)
    return log.add("raw", dest, take=take, source_file=src.name, format=audio.ext(dest),
                   duration_sec=audio.duration(dest), sha256=sha256(dest), note=note)


def record_take(ctx, project, seconds, note=""):
    log = audio_log(ctx, project)
    take = log.next_take()
    dest = _unique(voice_dir(ctx, project) / "raw" / f"take-{take:03d}_mic.wav")
    audio.record(dest, seconds)
    _protect(dest)
    return log.add("raw", dest, take=take, source_file="microphone", format="wav",
                   duration_sec=audio.duration(dest), sha256=sha256(dest), note=note)


def trim_audio(ctx, project, audio_id, start, end=None):
    log = audio_log(ctx, project)
    item = log.get(audio_id)
    src = log.path_of(item)
    dest = _unique(voice_dir(ctx, project) / "edited" / f"{Path(item['file']).stem}_trim{src.suffix}")
    audio.trim(src, dest, start, end)
    return log.add("edited", dest, parent=item["id"], trim=[start, end], format=audio.ext(dest),
                   duration_sec=audio.duration(dest), sha256=sha256(dest))


def select(ctx, project, audio_id):
    return audio_log(ctx, project).select(audio_id)


# ------------------------------------------------------------ AI voices

def resolve_voice(ctx, voice, engine, language, allow_missing=False):
    """Return (voice_id, voice_settings) for a preset id or 'clone:<name>'."""
    if voice.startswith("clone:"):
        data = clones.load_clone(ctx, voice.split(":", 1)[1])
        clones.assert_usable(ctx, data)
        voice_id = data["engine_voice_ids"].get(engine.name)
        if not voice_id:
            raise FactoryError(f"Clone '{data['name']}' has not been created on engine '{engine.name}'")
        return voice_id, {}
    preset = get_preset(ctx, voice)
    if language not in preset["languages"]:
        raise FactoryError(f"Preset '{voice}' does not support language '{language}'")
    voice_id = preset["engine_voices"].get(engine.name, {}).get("voice_id")
    if not voice_id and allow_missing:
        voice_id = "<voice_id not set>"
    if not voice_id:
        raise FactoryError(f"Preset '{voice}' has no voice_id for engine '{engine.name}'. "
                           "Set it in config/voice_presets.json")
    return voice_id, dict(preset["settings"])


def _require_confirmation(engine, confirm, message):
    if engine.sends_data_externally and not confirm(message):
        raise FactoryError("Cancelled: nothing was sent.")


def text_to_speech(ctx, project, voice=None, engine_name=None, text=None, confirm=lambda m: False):
    voice = voice or project.meta["voice_preset"]
    engine = get_engine(ctx, engine_name)
    voice_id, settings = resolve_voice(ctx, voice, engine, project.language)
    text = text or project_narration(ctx, project)
    if not text.strip():
        raise FactoryError("The script has no narration yet (03_script/script.md)")
    _require_confirmation(engine, confirm,
                          f"Send {len(text.split())} words of script text to {engine.name}?")
    log = audio_log(ctx, project)
    dest = _unique(voice_dir(ctx, project) / "tts" / f"{log.next_id()}_{voice.replace(':', '-')}.{engine.output_ext}")
    meta = engine.text_to_speech(text, voice_id, project.language, settings, dest)
    return log.add("tts", dest, engine=engine.name, voice=voice, language=project.language,
                   format=audio.ext(dest), duration_sec=meta.get("duration_sec"), sha256=sha256(dest))


def convert_voice(ctx, project, audio_id, voice, engine_name=None, confirm=lambda m: False):
    engine = get_engine(ctx, engine_name)
    voice_id, settings = resolve_voice(ctx, voice, engine, project.language)
    log = audio_log(ctx, project)
    item = log.get(audio_id)
    if item["kind"] not in ("raw", "edited"):
        raise FactoryError("Convert a raw or edited recording (your own voice), not AI output")
    src = log.path_of(item)
    _require_confirmation(engine, confirm, f"Upload recording {item['id']} ({src.name}) to {engine.name}?")
    dest = _unique(voice_dir(ctx, project) / "converted" / f"{log.next_id()}_{voice.replace(':', '-')}.{engine.output_ext}")
    meta = engine.speech_to_speech(src, voice_id, project.language, settings, dest)
    return log.add("converted", dest, parent=item["id"], engine=engine.name, voice=voice,
                   language=project.language, format=audio.ext(dest),
                   duration_sec=meta.get("duration_sec"), sha256=sha256(dest))


# ------------------------------------------------------------ output

def export_audio(ctx, project, audio_id=None, fmt="wav"):
    if fmt not in ctx.config.voice_studio["export_formats"]:
        raise FactoryError(f"Export format must be one of: {', '.join(ctx.config.voice_studio['export_formats'])}")
    log = audio_log(ctx, project)
    audio_id = audio_id or log.data["selected"]
    if not audio_id:
        raise FactoryError("No audio selected. Choose one with: voice select <project> <id>")
    item = log.get(audio_id)
    src = log.path_of(item)
    dest = _unique(voice_dir(ctx, project) / "exports" / f"{project.id}_voiceover.{fmt}")
    audio.convert(src, dest)
    return log.add("export", dest, parent=item["id"], format=fmt,
                   duration_sec=audio.duration(dest), sha256=sha256(dest))


def history(ctx, brand=None):
    """All audio across all projects: [(project, item, file_exists)]."""
    rows = []
    for p in iter_projects(ctx, brand=brand):
        log = audio_log(ctx, p)
        for item in log.items:
            rows.append((p, item, log.path_of(item).exists()))
    return rows
