"""Mock engine: free, offline, deterministic. Used for development and tests.

- TTS writes a silent WAV whose length matches the text (≈ 2.5 words/second).
- Speech-to-speech copies the input audio, so length and pacing are preserved.
- Cloning returns a fake voice ID.
"""

import hashlib
import re
import shutil

from factory.voice_studio import audio
from factory.voice_studio.engines.base import EngineError, VoiceEngine


class MockEngine(VoiceEngine):
    name = "mock"
    sends_data_externally = False
    output_ext = "wav"

    def text_to_speech(self, text, voice_id, language, voice_settings, out_path):
        words = len(re.findall(r"\w+", text))
        speed = float(voice_settings.get("speed", 1.0) or 1.0)
        seconds = max(1.0, words / 2.5 / speed)
        audio.write_silence(out_path, seconds)
        return {"engine": self.name, "voice_id": voice_id, "words": words,
                "duration_sec": round(seconds, 3)}

    def speech_to_speech(self, in_path, voice_id, language, voice_settings, out_path):
        if audio.ext(in_path) == "wav":
            shutil.copy2(in_path, out_path)
        elif audio.has_ffmpeg():
            audio.convert(in_path, out_path)
        else:
            raise EngineError("Mock conversion of MP3/M4A needs FFmpeg; use a WAV file instead.")
        return {"engine": self.name, "voice_id": voice_id,
                "duration_sec": audio.duration(out_path)}

    def create_clone(self, name, sample_paths, description=""):
        digest = hashlib.sha256(name.encode() + b"".join(p.read_bytes()[:1024] for p in sample_paths))
        return f"mock-clone-{digest.hexdigest()[:10]}"
