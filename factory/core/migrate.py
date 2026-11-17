"""Project format upgrades (`python -m factory migrate`).

Projects record their format in project.json as "schema_version"
(missing = 1, Phase 1). Each step below upgrades a project by one version.

Safety rules for every step:
  - a step may only ADD missing files (see add_missing_file); it never
    overwrites, renames or deletes anything a user created;
  - the only change to project.json is the "schema_version" number;
  - steps are idempotent: running migrate again changes nothing;
  - the default is a preview; nothing is written without --apply.
"""

from factory.core.errors import display_path
from factory.core.projects import CURRENT_SCHEMA, iter_projects
from factory.core.templates import render_template


def add_missing_file(ctx, project, relative_path, template, values, apply):
    """Create a project file from a template only if it doesn't exist yet."""
    target = project.folder / relative_path
    if target.exists():
        return []
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        text = render_template(ctx.paths, template, values, project.meta.get("brand"), project.language)
        target.write_text(text, encoding="utf-8")
    return [f"add {display_path(target, project.folder)}"]


def _to_v2(ctx, project, apply):
    """v2 (M0): introduces the format number itself. No new files."""
    return []


def _to_v3(ctx, project, apply):
    """v3 (M2 Research Engine): structured source list 01_research/sources.csv."""
    return add_missing_file(ctx, project, "01_research/sources.csv", "sources.csv", {}, apply)


# version reached -> (description, step function)
STEPS = {
    2: ("record project format version", _to_v2),
    3: ("add 01_research/sources.csv", _to_v3),
}
assert max(STEPS) == CURRENT_SCHEMA, "every format version needs a migration step"


def plan(ctx, brand=None):
    """[(project, from_version, [actions])] for projects older than CURRENT_SCHEMA."""
    result = []
    for project in iter_projects(ctx, brand=brand):
        version = project.meta.get("schema_version", 1)
        if version >= CURRENT_SCHEMA:
            continue
        actions = []
        for target in range(version + 1, CURRENT_SCHEMA + 1):
            description, step = STEPS[target]
            actions += step(ctx, project, apply=False)
            actions.append(f"set format {target - 1} → {target} ({description})")
        result.append((project, version, actions))
    return result


def apply(ctx, brand=None):
    """Upgrade every older project. Returns the same structure as plan()."""
    done = []
    for project, version, _ in plan(ctx, brand):
        actions = []
        for target in range(version + 1, CURRENT_SCHEMA + 1):
            description, step = STEPS[target]
            actions += step(ctx, project, apply=True)
            project.meta["schema_version"] = target
            actions.append(f"set format {target - 1} → {target} ({description})")
        project.save()
        done.append((project, version, actions))
    return done
