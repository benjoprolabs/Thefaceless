"""Paths and configuration loading.

Every other module gets file locations from here, so the folder layout
is defined in exactly one place.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Paths:
    """All important locations, relative to a project root (overridable for tests)."""

    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.config = self.root / "config"
        self.templates = self.root / "templates"
        self.ideas = self.root / "ideas"
        self.ideas_csv = self.ideas / "ideas.csv"
        self.projects = self.root / "projects"
        self.assets = self.root / "assets"
        self.analytics = self.root / "analytics"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_channel(paths):
    return load_json(paths.config / "channel.json")


def load_stages(paths):
    return load_json(paths.config / "pipeline.json")["stages"]
