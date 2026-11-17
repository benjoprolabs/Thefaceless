"""Local audio utilities.

WAV is handled with Python's built-in `wave` module (no install needed).
MP3/M4A conversion, trimming and recording use FFmpeg/SoX *if installed*;
otherwise a clear error explains what to install.
"""

import platform
import shutil
import subprocess
import wave
from pathlib import Path

from factory.core.config import FactoryError


class AudioToolMissing(FactoryError):
    pass


def ext(path):
    return Path(path).suffix.lower().lstrip(".")


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def wav_info(path):
    with wave.open(str(path), "rb") as w:
        frames, rate = w.getnframes(), w.getframerate()
        return {"channels": w.getnchannels(), "sample_rate": rate,
                "sample_width": w.getsampwidth(), "duration_sec": round(frames / rate, 3)}


def duration(path):
    """Duration in seconds, or None if it can't be measured locally."""
    if ext(path) == "wav":
        try:
            return wav_info(path)["duration_sec"]
        except (wave.Error, EOFError):
            return None
    if shutil.which("ffprobe"):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(path)],
                             capture_output=True, text=True)
        try:
            return round(float(out.stdout.strip()), 3)
        except ValueError:
            return None
    return None


def write_silence(path, seconds, sample_rate=16000):
    """Write a silent mono 16-bit WAV (used by the mock engine)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * int(seconds * sample_rate))


def trim(src, dst, start, end=None):
    """Copy the [start, end) seconds of src into dst. Never modifies src."""
    if start < 0 or (end is not None and end <= start):
        raise FactoryError("Invalid trim range: need 0 <= start < end")
    if ext(src) == "wav" and ext(dst) == "wav":
        with wave.open(str(src), "rb") as r:
            rate = r.getframerate()
            total = r.getnframes()
            first = int(start * rate)
            last = total if end is None else min(total, int(end * rate))
            if first >= total:
                raise FactoryError("Trim start is beyond the end of the audio")
            r.setpos(first)
            frames = r.readframes(last - first)
            params = r.getparams()
        with wave.open(str(dst), "wb") as w:
            w.setparams(params)
            w.writeframes(frames)
        return
    _ffmpeg(["-i", str(src), "-ss", str(start)] + (["-to", str(end)] if end else []) + [str(dst)])


def convert(src, dst):
    """Convert between formats (e.g. WAV → MP3). Same format = plain copy."""
    if ext(src) == ext(dst):
        shutil.copy2(src, dst)
        return
    _ffmpeg(["-i", str(src), str(dst)])


def _ffmpeg(args):
    if not has_ffmpeg():
        raise AudioToolMissing("This needs FFmpeg (free). Install it from https://ffmpeg.org, "
                               "or use WAV files, which work without it.")
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise FactoryError(f"FFmpeg failed: {result.stderr.strip()}")


# ---------------------------------------------------------- record / play

def recorder_command(out_path, seconds):
    """Pick a microphone recording command available on this computer, or None."""
    out = str(out_path)
    if shutil.which("rec"):  # SoX: macOS / Linux / Windows
        return ["rec", "-q", "-c", "1", "-r", "44100", out, "trim", "0", str(seconds)]
    if shutil.which("arecord"):  # Linux ALSA
        return ["arecord", "-q", "-f", "cd", "-d", str(int(seconds)), out]
    if shutil.which("ffmpeg"):
        system = platform.system()
        if system == "Darwin":
            return ["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation", "-i", ":0", "-t", str(seconds), out]
        if system == "Linux":
            return ["ffmpeg", "-y", "-loglevel", "error", "-f", "pulse", "-i", "default", "-t", str(seconds), out]
    return None


def record(out_path, seconds):
    cmd = recorder_command(out_path, seconds)
    if cmd is None:
        raise AudioToolMissing("No microphone recorder found. Install SoX (`rec`) or FFmpeg, "
                               "or record in any app (Voice Memos, Audacity...) and use `voice import`.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd)
    if result.returncode != 0 or not out_path.exists():
        raise FactoryError("Recording failed. Check microphone permissions.")


def player_command(path):
    for tool, args in (("afplay", []), ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error"]),
                       ("paplay", []), ("aplay", ["-q"])):
        if shutil.which(tool):
            if tool in ("paplay", "aplay") and ext(path) != "wav":
                continue
            return [tool] + args + [str(path)]
    return None


def play(path):
    cmd = player_command(path)
    if cmd is None:
        if platform.system() == "Windows":
            import os
            os.startfile(str(path))  # opens the default player
            return
        raise AudioToolMissing(f"No audio player found. Open the file manually: {path}")
    subprocess.run(cmd)
