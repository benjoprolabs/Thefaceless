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
    for field in ("id", "title", "language", "division", "format", "stage"):
        if not isinstance(meta[field], str) or not meta[field].strip():
            return f"'{field}' must be non-empty text"
    if not isinstance(meta["history"], list) or not all(
            isinstance(h, dict) and "stage" in h for h in meta["history"]):
        return "'history' must be a list of {\"stage\": ..., \"date\": ...} entries"
    if meta["stage"] not in [s["id"] for s in ctx.config.stages]:
        return f"unknown stage '{meta['stage']}'"
    if meta["language"] not in ctx.config.languages:
        return f"unknown language '{meta['language']}'"
    if meta["format"] not in ctx.config.formats:
        return f"unknown format '{meta['format']}'"
    seconds = meta.get("target_seconds")
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0):
        return "'target_seconds' must be a whole number of seconds"
    pubs = meta.get("publications")
    if pubs is not None and (not isinstance(pubs, list) or not all(
            isinstance(x, dict) and {"platform", "url", "date"} <= set(x) for x in pubs)):
        return "'publications' must be a list of {\"platform\", \"url\", \"date\"} entries"
    return None


def fill_defaults(ctx, meta, brand):
    """Optional fields added in later versions or removed by hand get safe
    defaults in memory (written to disk only when the project is next saved)."""
    meta.setdefault("brand", brand)
    meta.setdefault("target_seconds", ctx.config.formats[meta["format"]]["default_seconds"])
    meta.setdefault("publications", [])
    meta.setdefault("idea_id", "")
    first = meta["history"][0] if meta["history"] else {}
    meta.setdefault("created", first.get("date", ""))
    return meta


def location_problem(meta_path, meta):
    """The project.json must agree with the folder it is stored in:
    brands/<brand>/<language>/<division>/<id>/project.json"""
    folder = meta_path.parent
    division, language, brand = folder.parent.name, folder.parent.parent.name, folder.parents[2].name
    if meta["id"] != folder.name:
        return (f"its id '{meta['id']}' doesn't match the folder name '{folder.name}' "
                "(was the folder copied or renamed? Rename the folder or fix 'id')")
    if meta["language"] != language:
        return (f"it says language '{meta['language']}' but is stored in the '{language}' folder "
                f"(move it to brands/{brand}/{meta['language']}/{meta['division']}/ or fix 'language')")
    if meta["division"] != division:
        return (f"it says division '{meta['division']}' but is stored in the '{division}' folder "
                f"(move it to brands/{brand}/{language}/{meta['division']}/ or fix 'division')")
    if meta["brand"] != brand:
        return f"it says brand '{meta['brand']}' but is stored under brands/{brand}/"
    return None


def _rel(ctx, path):
    return path.relative_to(ctx.paths.root) if ctx.paths.root in path.parents else path


def load_checked(ctx, meta_path):
    """Load a project, or record a warning and return None if it is damaged."""
    try:
        meta = read_json(meta_path)
    except json.JSONDecodeError as e:
        problem = f"invalid JSON (line {e.lineno}, column {e.colno}: {e.msg})"
    except PermissionError:
        problem = "permission denied (your account can't read this file)"
    except OSError as e:
        problem = f"cannot be read ({e.strerror or e.__class__.__name__})"
    else:
        problem = project_problem(ctx, meta)
        if problem is None:
            fill_defaults(ctx, meta, meta_path.parents[3].name)
            problem = location_problem(meta_path, meta)
        if problem is None:
            return Project(meta_path.parent, meta)
    rel = _rel(ctx, meta_path)
    ctx.warnings[str(rel)] = f"Skipped damaged project {rel}: {problem}"
    return None


def iter_projects(ctx, brand=None, language=None, division=None):
    """Yield all valid projects, optionally filtered. Sorted by path.

    Damaged projects are skipped and reported in ctx.warnings. Project IDs must
    be unique within a brand: if two folders hold the same ID (e.g. a copied
    folder), *all* copies are skipped with a warning, so nothing is shown or
    counted twice. The whole brand is scanned so duplicates are found even
    when filtering by language or division."""
    projects = []
    for meta_path in sorted(ctx.paths.brands.glob(f"{brand or '*'}/*/*/*/{PROJECT_FILE}")):
        project = load_checked(ctx, meta_path)
        if project is not None:
            projects.append(project)
    by_id = {}
    for project in projects:
        by_id.setdefault((project.meta["brand"], project.id), []).append(project)
    for (brand_id, project_id), copies in by_id.items():
        if len(copies) > 1:
            places = " and ".join(str(_rel(ctx, c.folder)) for c in copies)
            ctx.warnings[f"duplicate:{brand_id}:{project_id}"] = (
                f"Skipped duplicate project id '{project_id}' found in {places}. "
                "Each project needs its own id: rename the copy's folder and its 'id', or remove it.")
    for project in projects:
        if len(by_id[(project.meta["brand"], project.id)]) > 1:
            continue
        if language and project.language != language:
            continue
        if division and project.meta["division"] != division:
            continue
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
        hint = " (some projects were skipped because they are damaged or duplicated; see the warnings below)" if ctx.warnings else ""
        raise FactoryError(f"No project matches '{project_id}'{hint}. See: python -m factory status")
    names = ", ".join(p.id for p in partial)
    raise FactoryError(f"'{project_id}' matches several projects: {names}")
