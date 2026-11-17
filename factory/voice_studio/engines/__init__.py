"""Engine registry. To add an engine: write a VoiceEngine subclass, add it to
ENGINES, and add its settings under "engines" in config/voice_studio.json."""

from factory.core.config import FactoryError
from factory.voice_studio.engines.elevenlabs import ElevenLabsEngine
from factory.voice_studio.engines.mock import MockEngine

ENGINES = {
    MockEngine.name: MockEngine,
    ElevenLabsEngine.name: ElevenLabsEngine,
}


def get_engine(ctx, name=None):
    cfg = ctx.config.voice_studio
    name = name or cfg["default_engine"]
    if name not in ENGINES:
        raise FactoryError(f"Unknown engine '{name}'. Available: {', '.join(ENGINES)}")
    return ENGINES[name](cfg["engines"].get(name, {}))
