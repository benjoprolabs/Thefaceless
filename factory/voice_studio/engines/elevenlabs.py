"""ElevenLabs engine (initial production engine).

PHASE 1: NO NETWORK CALLS ARE MADE. Every method builds the exact request it
*would* send (so the workflow and settings can be reviewed with --dry-run),
then raises PaidAPIDisabled. Enabling real calls is a later, explicit step:
implement `_send()` and set "calls_enabled": true in config/voice_studio.json.

The API key is only ever read from the environment variable named in
config (default ELEVENLABS_API_KEY). It is never stored in files or printed.
Verify endpoints and model IDs against the current ElevenLabs API docs
before enabling.
"""

import os

from factory.voice_studio.engines.base import EngineNotConfigured, PaidAPIDisabled, VoiceEngine

KEY_PLACEHOLDER = "<read from $%s at call time>"


class ElevenLabsEngine(VoiceEngine):
    name = "elevenlabs"
    sends_data_externally = True
    output_ext = "mp3"

    # --- configuration -----------------------------------------------------
    @property
    def key_env(self):
        return self.settings.get("api_key_env", "ELEVENLABS_API_KEY")

    def api_key_present(self):
        return bool(os.environ.get(self.key_env))

    def _headers(self):
        return {"xi-api-key": KEY_PLACEHOLDER % self.key_env}

    def _url(self, path):
        return self.settings.get("base_url", "https://api.elevenlabs.io").rstrip("/") + path

    @staticmethod
    def _voice_settings(s):
        keys = ("stability", "similarity_boost", "style", "speed")
        return {k: s[k] for k in keys if k in s}

    # --- request builders (pure, testable, no network) --------------------
    def build_tts_request(self, text, voice_id, language, voice_settings):
        return {
            "method": "POST",
            "url": self._url(f"/v1/text-to-speech/{voice_id}"),
            "query": {"output_format": self.settings.get("output_format", "mp3_44100_128")},
            "headers": self._headers(),
            # The multilingual model detects English/Malay from the text itself.
            "json": {"text": text, "model_id": self.settings.get("tts_model"),
                     "voice_settings": self._voice_settings(voice_settings)},
        }

    def build_sts_request(self, in_path, voice_id, voice_settings):
        return {
            "method": "POST",
            "url": self._url(f"/v1/speech-to-speech/{voice_id}"),
            "query": {"output_format": self.settings.get("output_format", "mp3_44100_128")},
            "headers": self._headers(),
            "multipart": {"audio": str(in_path), "model_id": self.settings.get("sts_model"),
                          "voice_settings": self._voice_settings(voice_settings)},
        }

    def build_clone_request(self, name, sample_paths, description=""):
        return {
            "method": "POST",
            "url": self._url("/v1/voices/add"),
            "headers": self._headers(),
            "multipart": {"name": name, "description": description,
                          "files": [str(p) for p in sample_paths]},
        }

    # --- engine interface -------------------------------------------------
    def text_to_speech(self, text, voice_id, language, voice_settings, out_path):
        return self._send(self.build_tts_request(text, voice_id, language, voice_settings))

    def speech_to_speech(self, in_path, voice_id, language, voice_settings, out_path):
        return self._send(self.build_sts_request(in_path, voice_id, voice_settings))

    def create_clone(self, name, sample_paths, description=""):
        return self._send(self.build_clone_request(name, sample_paths, description))

    def _send(self, request):
        if not self.api_key_present():
            raise EngineNotConfigured(f"Set the {self.key_env} environment variable first "
                                      "(never put the key in a file in this repository).")
        raise PaidAPIDisabled("ElevenLabs API calls are disabled in Phase 1. "
                              f"Would send: {request['method']} {request['url']}")
