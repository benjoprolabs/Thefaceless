"""Project model: one folder per video.

Location: brands/<brand>/<language>/<division>/<project_id>/
Metadata: project.json in that folder.
"""

from factory.core.config import FactoryError
from factory.core.files import read_json, write_json

PROJECT_FILE = "project.json"


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


def iter_projects(ctx, brand=None, language=None, division=None):
    """Yield all projects, optionally filtered. Sorted by path."""
    pattern = f"{brand or '*'}/{language or '*'}/{division or '*'}/*/{PROJECT_FILE}"
    for meta_path in sorted(ctx.paths.brands.glob(pattern)):
        yield Project.load(meta_path.parent)


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
        raise FactoryError(f"No project matches '{project_id}'. See: python -m factory status")
    names = ", ".join(p.id for p in partial)
    raise FactoryError(f"'{project_id}' matches several projects: {names}")
