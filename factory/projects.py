"""Create and inspect video projects (one folder per video under projects/)."""

import json
import re
from datetime import date

from factory.config import load_channel, load_stages
from factory.templates import render

PROJECT_FILE = "project.json"


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50].rstrip("-") or "untitled"


def create_project(paths, title, fmt=None, idea_id="", today=None):
    """Create a project folder with stage subfolders and filled-in templates.

    Returns the path of the new project folder.
    """
    channel = load_channel(paths)
    stages = load_stages(paths)
    fmt = fmt or channel["default_format"]
    if fmt not in channel["formats"]:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(channel['formats'])}")

    today = today or date.today().isoformat()
    project_id = f"{today}_{slugify(title)}"
    folder = paths.projects / project_id
    if folder.exists():
        raise FileExistsError(f"Project already exists: {folder}")

    spec = channel["formats"][fmt]
    values = {
        "project_id": project_id,
        "idea_id": idea_id or "-",
        "title": title,
        "format": fmt,
        "created": today,
        "target_seconds": spec["target_seconds"],
        "target_words": round(spec["target_seconds"] / 60 * channel["words_per_minute"]),
        "resolution": spec["resolution"],
        "aspect_ratio": spec["aspect_ratio"],
    }

    folder.mkdir(parents=True)
    for stage in stages:
        if not stage["folder"]:
            continue
        stage_dir = folder / stage["folder"]
        stage_dir.mkdir()
        for name in stage["templates"]:
            text = (paths.templates / name).read_text(encoding="utf-8")
            (stage_dir / name).write_text(render(text, values), encoding="utf-8")
        if not stage["templates"]:
            (stage_dir / ".gitkeep").touch()

    meta = {
        "id": project_id,
        "title": title,
        "idea_id": idea_id,
        "format": fmt,
        "stage": stages[0]["id"],
        "created": today,
        "history": [{"stage": stages[0]["id"], "date": today}],
    }
    write_meta(folder, meta)
    return folder


def write_meta(folder, meta):
    (folder / PROJECT_FILE).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def read_meta(folder):
    return json.loads((folder / PROJECT_FILE).read_text(encoding="utf-8"))


def list_projects(paths):
    if not paths.projects.exists():
        return []
    return [
        read_meta(p)
        for p in sorted(paths.projects.iterdir())
        if (p / PROJECT_FILE).exists()
    ]
