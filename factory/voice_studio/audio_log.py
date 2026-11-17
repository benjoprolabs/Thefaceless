"""Per-project audio history: 05_voice/audio_log.json.

Every file Voice Studio creates gets an entry (A001, A002...) recording what it
is, where it came from (parent), which engine/voice made it, and its checksum.
"""

from factory.core.config import FactoryError
from factory.core.files import read_json, today, write_json

KINDS = ("raw", "edited", "tts", "converted", "export")
LOG_NAME = "audio_log.json"


class AudioLog:
    def __init__(self, voice_dir):
        self.voice_dir = voice_dir
        self.path = voice_dir / LOG_NAME
        self.data = read_json(self.path) if self.path.exists() else {"selected": None, "items": []}

    @property
    def items(self):
        return self.data["items"]

    def next_id(self):
        return f"A{len(self.items) + 1:03d}"

    def next_take(self):
        return 1 + sum(1 for i in self.items if i["kind"] == "raw")

    def add(self, kind, file, **fields):
        if kind not in KINDS:
            raise ValueError(kind)
        item = {"id": self.next_id(), "kind": kind,
                "file": file.relative_to(self.voice_dir).as_posix(), "created": today()}
        item.update({k: v for k, v in fields.items() if v is not None})
        self.items.append(item)
        self.save()
        return item

    def get(self, audio_id):
        for item in self.items:
            if item["id"].lower() == audio_id.lower():
                return item
        raise FactoryError(f"No audio '{audio_id}' in this project. See: voice list")

    def path_of(self, item):
        return self.voice_dir / item["file"]

    def select(self, audio_id):
        item = self.get(audio_id)
        if item["kind"] == "export":
            raise FactoryError("Select a take, TTS or converted file, not an export")
        self.data["selected"] = item["id"]
        self.save()
        return item

    def save(self):
        write_json(self.path, self.data)
