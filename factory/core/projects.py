"""Project model: one folder per video.

Location: brands/<brand>/<language>/<division>/<project_id>/
Metadata: project.json in that folder.

A damaged project.json (invalid JSON, missing fields, unknown stage...) never
breaks listings: the project is skipped and reported in ctx.warnings, which
the CLI prints after every command.
"""

import json

from factory.core.config import FactoryError
from factory.core.files import read_json, write_json

PROJECT_FILE = "project.json"
REQUIRED_FIELDS = ("id", "title", "language", "division", "format", "stage", "history")


class Project:
    def __init__(self, folder, meta):
        self.folder = folder
        self.meta = meta

    @property
    def id(self):
        return self.meta["id"]

    @property
    def language(self):
        return self.meta["language"]

    @property
    def stage(self):
        return self.meta["stage"]

    def stage_dir(self, ctx, stage_id):
        return self.folder / ctx.config.stage(stage_id)["folder"]

    def save(self):
        write_json(self.folder / PROJECT_FILE, self.meta)

    @classmethod
    def load(cls, folder):
        return cls(folder, read_json(folder / PROJECT_FILE))


def project_problem(ctx, meta):
    """Return a description of what is wrong with project metadata, or None."""
    if not isinstance(meta, dict):
        return "project.json must contain a JSON object"
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        return f"missing field(s): {', '.join(missing)}"
    if not isinstance(meta["history"], list):
        return "'history' must be a list"
    if meta["stage"] not in [s["id"] for s in ctx.config.stages]:
        return f"unknown stage '{meta['stage']}'"
    if meta["language"] not in ctx.config.languages:
        return f"unknown language '{meta['language']}'"
    if meta["format"] not in ctx.config.formats:
        return f"unknown format '{meta['format']}'"
    return None


def load_checked(ctx, meta_path):
    """Load a project, or record a warning and return None if it is damaged."""
    try:
        meta = read_json(meta_path)
    except json.JSONDecodeError as e:
        problem = f"invalid JSON (line {e.lineno}, column {e.colno}: {e.msg})"
    except (OSError, UnicodeDecodeError) as e:
        problem = f"cannot be read ({e.__class__.__name__})"
    else:
        problem = project_problem(ctx, meta)
        if problem is None:
            return Project(meta_path.parent, meta)
    rel = meta_path.relative_to(ctx.paths.root) if ctx.paths.root in meta_path.parents else meta_path
    ctx.warnings[str(rel)] = f"Skipped damaged project {rel}: {problem}"
    return None


def iter_projects(ctx, brand=None, language=None, division=None):
    """Yield all valid projects, optionally filtered. Sorted by path.
    Damaged projects are skipped and reported in ctx.warnings."""
    pattern = f"{brand or '*'}/{language or '*'}/{division or '*'}/*/{PROJECT_FILE}"
    for meta_path in sorted(ctx.paths.brands.glob(pattern)):
        project = load_checked(ctx, meta_path)
        if project is not None:
            yield project


def find_project(ctx, project_id):
    """Find a project by exact ID, or by a unique part of its ID."""
    projects = list(iter_projects(ctx))
    exact = [p for p in projects if p.id == project_id]
    if exact:
        return exact[0]
    partial = [p for p in projects if project_id in p.id]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        hint = " (some projects were skipped because their project.json is damaged)" if ctx.warnings else ""
        raise FactoryError(f"No project matches '{project_id}'{hint}. See: python -m factory status")
    names = ", ".join(p.id for p in partial)
    raise FactoryError(f"'{project_id}' matches several projects: {names}")
