"""The voice engine interface. Every engine (mock, ElevenLabs, a future local
model...) implements these methods, so the rest of the system never needs to
know which engine is in use.
"""

from abc import ABC, abstractmethod

from factory.core.config import FactoryError


class EngineError(FactoryError):
    pass


class EngineNotConfigured(EngineError):
    """Missing API key, voice ID or similar setup."""


class PaidAPIDisabled(EngineError):
    """Raised instead of making a paid API call while calls are disabled."""


class VoiceEngine(ABC):
    name = "base"
    #: True if the engine sends text/audio off this computer. The service layer
    #: asks the user to confirm before any such call.
    sends_data_externally = False
    #: File extension the engine produces.
    output_ext = "wav"

    def __init__(self, settings=None):
        self.settings = settings or {}

    @abstractmethod
    def text_to_speech(self, text, voice_id, language, voice_settings, out_path):
        """Write speech for `text` to out_path. Return a metadata dict."""

    @abstractmethod
    def speech_to_speech(self, in_path, voice_id, language, voice_settings, out_path):
        """Re-voice the recording at in_path, keeping emotion and pacing. Return metadata."""

    @abstractmethod
    def create_clone(self, name, sample_paths, description=""):
        """Create a voice clone from the owner's samples. Return the engine's voice ID."""

    def describe(self):
        return self.settings.get("description", "")
