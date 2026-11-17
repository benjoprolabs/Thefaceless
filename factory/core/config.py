"""File locations and configuration loading.

Every module asks `Paths` where things live, so the folder layout is defined
in exactly one place. Tests pass a temporary root to `Paths`.
"""

import json
from pathlib import Path

from factory.core.errors import FactoryError, display_path  # noqa: F401  (FactoryError re-exported)
from factory.core.files import read_json

ROOT = Path(__file__).resolve().parent.parent.parent

# Minimal shape of each settings file, checked when it is loaded so that a
# broken or hand-edited file gives a clear message instead of a crash later.
#   "keys":  required top-level keys
#   "each":  every top-level value must be an object with these keys
#   "list":  (key, item_keys): data[key] must be a list of objects with item_keys
SCHEMAS = {
    "settings": {"keys": ["default_brand", "default_language"]},
    "languages": {"each": ["name", "words_per_minute"]},
    "formats": {"each": ["label", "min_seconds", "max_seconds", "default_seconds",
                         "aspect_ratio", "resolution", "platforms"]},
    "divisions": {"each": ["name", "name_ms", "description", "visual_style", "notes"]},
    "pipeline": {"keys": ["stages"], "list": ("stages", ["id", "folder", "label", "module", "templates"])},
    "platforms": {"each": ["label", "domains"]},
    "visual_styles": {"each": ["description", "music_mood", "caption_style"]},
    "rules": {"keys": ["script"]},
    "brand": {"keys": ["id", "name", "divisions", "channels"],
              "list": ("channels", ["id", "name", "language", "platforms"])},
}


def load_settings_file(path, schema, root):
    """Load and shape-check a settings JSON file; raise FactoryError if broken."""
    rel = display_path(path, root)
    fix = f"Fix the file, or restore the original with: git checkout -- {rel}"
    try:
        data = read_json(path)
    except json.JSONDecodeError as e:
        raise FactoryError(f"{rel} is not valid JSON (line {e.lineno}, column {e.colno}: {e.msg}).\n"
                           f"  {fix}") from None

    def broken(problem):
        return FactoryError(f"{rel} has a problem: {problem}.\n  {fix}")

    if not isinstance(data, dict):
        raise broken("it must contain a JSON object { ... }")
    missing = [k for k in schema.get("keys", []) if k not in data]
    if missing:
        raise broken(f"missing {', '.join(repr(k) for k in missing)}")
    for name, entry in data.items() if "each" in schema else ():
        if not isinstance(entry, dict):
            raise broken(f"'{name}' must be an object {{ ... }}")
        missing = [k for k in schema["each"] if k not in entry]
        if missing:
            raise broken(f"'{name}' is missing {', '.join(repr(k) for k in missing)}")
    if "list" in schema:
        key, item_keys = schema["list"]
        items = data[key]
        if not isinstance(items, list):
            raise broken(f"'{key}' must be a list [ ... ]")
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise broken(f"item {i} of '{key}' must be an object {{ ... }}")
            missing = [k for k in item_keys if k not in item]
            if missing:
                raise broken(f"item {i} of '{key}' is missing {', '.join(repr(k) for k in missing)}")
    return data


class Paths:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.config = self.root / "config"
        self.templates = self.root / "templates"
        self.brands = self.root / "brands"
        self.assets = self.root / "assets"
        self.asset_register = self.assets / "register.csv"

    # Brand / language locations -------------------------------------------
    def brand_dir(self, brand):
        return self.brands / brand

    def language_dir(self, brand, language):
        return self.brands / brand / language

    def ideas_csv(self, brand, language):
        return self.language_dir(brand, language) / "ideas.csv"

    def division_dir(self, brand, language, division):
        return self.language_dir(brand, language) / division


class Config:
    """Read-only access to everything in config/ (loaded lazily, cached)."""

    def __init__(self, paths):
        self.paths = paths
        self._cache = {}

    def _load(self, name):
        if name not in self._cache:
            self._cache[name] = load_settings_file(self.paths.config / f"{name}.json",
                                                   SCHEMAS.get(name, {}), self.paths.root)
        return self._cache[name]

    @property
    def settings(self):
        return self._load("settings")

    @property
    def languages(self):
        return self._load("languages")

    @property
    def formats(self):
        return self._load("formats")

    @property
    def divisions(self):
        return self._load("divisions")

    @property
    def stages(self):
        return self._load("pipeline")["stages"]

    @property
    def rules(self):
        return self._load("rules")

    @property
    def platforms(self):
        return self._load("platforms")

    @property
    def visual_styles(self):
        return self._load("visual_styles")

    def brand(self, brand_id=None):
        brand_id = brand_id or self.settings["default_brand"]
        path = self.paths.brand_dir(brand_id) / "brand.json"
        if not path.exists():
            raise FactoryError(f"Unknown brand '{brand_id}' (missing {path})")
        return load_settings_file(path, SCHEMAS["brand"], self.paths.root)

    def brand_ids(self):
        return sorted(p.parent.name for p in self.paths.brands.glob("*/brand.json"))

    def stage(self, stage_id):
        for s in self.stages:
            if s["id"] == stage_id:
                return s
        raise FactoryError(f"Unknown stage '{stage_id}'")

    def stage_index(self, stage_id):
        return [s["id"] for s in self.stages].index(stage_id)


class Context:
    """Bundle passed to every command: paths + config."""

    def __init__(self, root=ROOT):
        self.paths = Paths(root)
        self.config = Config(self.paths)
        # Non-fatal problems found while running a command (e.g. damaged projects).
        # Keyed by file path so each problem is reported once.
        self.warnings = {}
