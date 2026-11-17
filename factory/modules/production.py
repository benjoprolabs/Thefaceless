"""Module 6: Production Manager. Create projects, track and advance stages.

A project can only advance when every '- [ ]' checklist item in the current
stage's Markdown files is ticked (use --force to override).
"""

from factory.core.config import FactoryError
from factory.core.files import slugify, today, unchecked_items
from factory.core.options import (add_brand, add_division, add_language, brand_id,
                                  check_division, check_format, check_language)
from factory.core.projects import Project, find_project, iter_projects
from factory.core.templates import render_template
from factory.modules import ideas as ideas_mod


def template_values(ctx, brand, language, division, fmt, seconds, title, project_id, idea_id, created):
    brand_cfg = ctx.config.brand(brand)
    lang = ctx.config.languages[language]
    div = ctx.config.divisions[division]
    spec = ctx.config.formats[fmt]
    return {
        "project_id": project_id, "title": title, "idea_id": idea_id or "-", "created": created,
        "brand_name": brand_cfg["name"], "language": language, "language_name": lang["name"],
        "division": division, "division_name": div["name"] if language == "en" else div["name_ms"],
        "division_notes": div["notes"], "visual_style": div["visual_style"],
        "format": fmt, "format_label": spec["label"], "aspect_ratio": spec["aspect_ratio"],
        "resolution": spec["resolution"], "min_seconds": spec["min_seconds"],
        "max_seconds": spec["max_seconds"], "target_seconds": seconds,
        "words_per_minute": lang["words_per_minute"],
        "target_words": round(seconds / 60 * lang["words_per_minute"]),
    }


def create_project(ctx, title, language, division, fmt="short", brand=None, seconds=None,
                   idea_id="", created=None):
    brand = brand or ctx.config.settings["default_brand"]
    check_language(ctx, language)
    check_division(ctx, division, brand)
    check_format(ctx, fmt)
    spec = ctx.config.formats[fmt]
    seconds = seconds or spec["default_seconds"]
    if not spec["min_seconds"] <= seconds <= spec["max_seconds"]:
        raise FactoryError(f"{spec['label']} must be {spec['min_seconds']}–{spec['max_seconds']} seconds")

    created = created or today()
    project_id = f"{created}_{slugify(title)}"
    if any(p.id == project_id for p in iter_projects(ctx, brand=brand)):
        raise FactoryError(f"Project already exists: {project_id}")
    folder = ctx.paths.division_dir(brand, language, division) / project_id

    values = template_values(ctx, brand, language, division, fmt, seconds, title,
                             project_id, idea_id, created)
    folder.mkdir(parents=True)
    for stage in ctx.config.stages:
        stage_dir = folder / stage["folder"]
        stage_dir.mkdir()
        for name in stage["templates"]:
            text = render_template(ctx.paths, name, values, brand=brand, language=language)
            (stage_dir / name).write_text(text, encoding="utf-8")

    first = ctx.config.stages[0]["id"]
    project = Project(folder, {
        "id": project_id, "title": title, "brand": brand, "language": language,
        "division": division, "format": fmt, "target_seconds": seconds,
        "idea_id": idea_id,
        "stage": first, "created": created,
        "history": [{"stage": first, "date": created}],
        "publications": [],
    })
    project.save()
    if idea_id:
        ideas_mod.link_project(ctx, brand, language, idea_id, project_id)
    return project


def stage_blockers(ctx, project):
    """Unticked checklist items in the current stage's Markdown files."""
    stage_dir = project.stage_dir(ctx, project.stage)
    blockers = []
    for md in sorted(stage_dir.glob("*.md")):
        blockers += [f"{md.name}: {item}" for item in unchecked_items(md.read_text(encoding="utf-8"))]
    return blockers


def advance(ctx, project, force=False, day=None):
    stages = ctx.config.stages
    index = ctx.config.stage_index(project.stage)
    if index == len(stages) - 1:
        raise FactoryError("Project is already at the last stage (Analytics).")
    blockers = stage_blockers(ctx, project)
    if blockers and not force:
        raise FactoryError("Stage checklist not complete:\n  - " + "\n  - ".join(blockers)
                           + "\nTick the boxes, or use --force.")
    new_stage = stages[index + 1]["id"]
    project.meta["stage"] = new_stage
    entry = {"stage": new_stage, "date": day or today()}
    if blockers:
        entry["forced"] = True
    project.meta["history"].append(entry)
    project.save()
    return new_stage


# ---------------------------------------------------------------- commands

def cmd_new(args, ctx):
    brand = brand_id(args, ctx)
    title, language, division, fmt = args.title, args.lang, args.division, args.format
    if args.idea:
        language, idea = ideas_mod.find_idea(ctx, brand, args.idea)
        if idea["project_id"]:
            raise FactoryError(f"Idea {idea['id']} already has project {idea['project_id']}")
        title = title or idea["title"]
        division = division or idea["division"]
        fmt = fmt or idea["format"]
    if not (title and language and division):
        raise FactoryError("Give a title with --lang and --division, or use --idea IDEA-ID")
    project = create_project(ctx, title, language, division, fmt or "short", brand=brand,
                             seconds=args.seconds, idea_id=args.idea or "")
    print(f"Created: {project.folder.relative_to(ctx.paths.root)}")
    print("Next: fill in 01_research/research.md, then: python -m factory advance " + project.id)
    return 0


def cmd_status(args, ctx):
    brand = brand_id(args, ctx)
    projects = list(iter_projects(ctx, brand=brand, language=args.lang, division=args.division))
    if not projects:
        print("No projects yet. Create one with: python -m factory new --idea EN-002")
        return 0
    total = len(ctx.config.stages)
    print(f"{'PROJECT':<48} {'LANG':<4} {'DIVISION':<18} {'FMT':<5} STAGE")
    for p in projects:
        n = ctx.config.stage_index(p.stage) + 1
        label = ctx.config.stage(p.stage)["label"]
        print(f"{p.id:<48} {p.language:<4} {p.meta['division']:<18} {p.meta['format']:<5} {n:>2}/{total} {label}")
    return 0


def cmd_show(args, ctx):
    p = find_project(ctx, args.project)
    m = p.meta
    print(f"{m['title']}  [{m['id']}]")
    print(f"  Folder   : {p.folder.relative_to(ctx.paths.root)}")
    print(f"  Brand    : {m['brand']}   Language: {m['language']}   Division: {m['division']}")
    print(f"  Format   : {m['format']}, target {m['target_seconds']} s")
    print("  Workflow :")
    current = ctx.config.stage_index(p.stage)
    for i, stage in enumerate(ctx.config.stages):
        mark = "✔" if i < current else ("▶" if i == current else " ")
        print(f"    {mark} {i + 1:>2}. {stage['label']:<18} ({stage['module']})")
    blockers = stage_blockers(ctx, p)
    if blockers:
        print(f"  Open checklist items in this stage: {len(blockers)}")
    for pub in m.get("publications", []):
        print(f"  Published: {pub['platform']} {pub['date']} {pub['url']}")
    return 0


def cmd_advance(args, ctx):
    p = find_project(ctx, args.project)
    new_stage = advance(ctx, p, force=args.force)
    print(f"{p.id} → {ctx.config.stage(new_stage)['label']}")
    return 0


def register(sub):
    new = sub.add_parser("new", help="Production Manager: create a project")
    new.add_argument("title", nargs="?")
    add_brand(new)
    add_language(new)
    add_division(new)
    new.add_argument("--format", help="short (15–90 s) or long (5–20 min)")
    new.add_argument("--seconds", type=int, help="target length in seconds")
    new.add_argument("--idea", help="create from an idea ID, e.g. EN-002")
    new.set_defaults(func=cmd_new)

    st = sub.add_parser("status", help="Production Manager: list projects and stages")
    add_brand(st)
    add_language(st)
    add_division(st)
    st.set_defaults(func=cmd_status)

    sh = sub.add_parser("show", help="Production Manager: project details and workflow")
    sh.add_argument("project")
    sh.set_defaults(func=cmd_show)

    ad = sub.add_parser("advance", help="Production Manager: move project to next stage")
    ad.add_argument("project")
    ad.add_argument("--force", action="store_true", help="advance even with unticked checklist items")
    ad.set_defaults(func=cmd_advance)
