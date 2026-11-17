"""File locations and configuration loading.

Every module asks `Paths` where things live, so the folder layout is defined
in exactly one place. Tests pass a temporary root to `Paths`.
"""

from pathlib import Path

from factory.core.files import read_json

ROOT = Path(__file__).resolve().parent.parent.parent


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
            self._cache[name] = read_json(self.paths.config / f"{name}.json")
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
    def visual_styles(self):
        return self._load("visual_styles")

    def brand(self, brand_id=None):
        brand_id = brand_id or self.settings["default_brand"]
        path = self.paths.brand_dir(brand_id) / "brand.json"
        if not path.exists():
            raise FactoryError(f"Unknown brand '{brand_id}' (missing {path})")
        return read_json(path)

    def brand_ids(self):
        return sorted(p.parent.name for p in self.paths.brands.glob("*/brand.json"))

    def stage(self, stage_id):
        for s in self.stages:
            if s["id"] == stage_id:
                return s
        raise FactoryError(f"Unknown stage '{stage_id}'")

    def stage_index(self, stage_id):
        return [s["id"] for s in self.stages].index(stage_id)


class FactoryError(Exception):
    """A user-facing error: the CLI prints the message and exits with code 1."""


class Context:
    """Bundle passed to every command: paths + config."""

    def __init__(self, root=ROOT):
        self.paths = Paths(root)
        self.config = Config(self.paths)
