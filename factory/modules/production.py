"""Module 6: Production Manager. Create projects, track and advance stages.

A project can only advance when every '- [ ]' checklist item in the current
stage's Markdown files is ticked (use --force to override).
"""

import shutil
import unicodedata

from factory.core.config import FactoryError
from factory.core.checks import FAIL, WARN, failures, format_finding, run_checks
from factory.core.errors import describe_os_error, display_path
from factory.core.files import has_checklist, read_text, title_slug, today, unchecked_items
from factory.core.options import (add_brand, add_division, add_language, brand_id,
                                  check_division, check_format, check_language)
from factory.core import migrate as migrate_mod
from factory.core.projects import CURRENT_SCHEMA, Project, find_project, iter_projects
from factory.core.templates import find_template, render_template
from factory.modules import ideas as ideas_mod
from factory.modules import scripts as _scripts  # noqa: F401  (registers the script checks)


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


def _same_title(a, b):
    return unicodedata.normalize("NFC", a.strip()).casefold() == unicodedata.normalize("NFC", b.strip()).casefold()


def new_project_id(ctx, brand, language, title, created):
    """<date>_<language>_<slug>, unique within the brand.

    The language is part of the ID, so the same title in English and Malay on
    the same day can't collide. The same title in the same language on the
    same day is refused (almost always an accidental repeat). A different title
    that happens to give the same slug gets -2, -3, ... A folder with the ID
    that can't be read (damaged project) is never overwritten or guessed past."""
    base = f"{created}_{language}_{title_slug(title)}"
    projects = {p.id: p for p in iter_projects(ctx, brand=brand)}
    for n in range(1, 1000):
        candidate = base if n == 1 else f"{base}-{n}"
        existing = projects.get(candidate)
        if existing is not None and _same_title(existing.meta["title"], title):
            raise FactoryError(f"A {ctx.config.languages[language]['name']} project with this title was "
                               f"already created on {created}: {candidate}")
        if existing is None:
            taken = sorted(ctx.paths.brand_dir(brand).glob(f"*/*/{candidate}"))
            if not taken:
                return candidate
            # A folder with this ID exists but isn't a readable project (damaged or
            # duplicated). Its title is unknown, so refuse rather than guess.
            raise FactoryError(f"A project folder with the ID {candidate} already exists but can't be read: "
                               f"{display_path(taken[0], ctx.paths.root)}. Fix or remove it first "
                               "(see the warnings from: python -m factory status)")
    raise FactoryError("Too many projects with similar titles today; choose a different title")


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
    if not title.strip():
        raise FactoryError("The title can't be empty")
    project_id = new_project_id(ctx, brand, language, title, created)
    folder = ctx.paths.division_dir(brand, language, division) / project_id
    if folder.exists():
        raise FactoryError(f"Folder already exists: {display_path(folder, ctx.paths.root)}")

    values = template_values(ctx, brand, language, division, fmt, seconds, title,
                             project_id, idea_id, created)
    first = ctx.config.stages[0]["id"]
    project = Project(folder, {
        "schema_version": CURRENT_SCHEMA,
        "id": project_id, "title": title, "brand": brand, "language": language,
        "division": division, "format": fmt, "target_seconds": seconds,
        "idea_id": idea_id,
        "stage": first, "created": created,
        "history": [{"stage": first, "date": created}],
        "publications": [],
    })
    folder.mkdir(parents=True)
    try:
        for stage in ctx.config.stages:
            stage_dir = folder / stage["folder"]
            stage_dir.mkdir()
            for name in stage["templates"]:
                text = render_template(ctx.paths, name, values, brand=brand, language=language)
                (stage_dir / name).write_text(text, encoding="utf-8")
        project.save()
    except OSError:
        # Don't leave a half-created project behind (it would block a retry).
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if idea_id:
        try:
            ideas_mod.link_project(ctx, brand, language, idea_id, project_id)
        except OSError as e:
            raise FactoryError(
                f"Project {project_id} was created, but the idea list could not be updated.\n"
                f"{describe_os_error(e, ctx.paths.root)}\n"
                f"  Then set {idea_id} to status 'in_production' and project_id '{project_id}' "
                f"in {display_path(ctx.paths.ideas_csv(brand, language), ctx.paths.root)}") from None
    return project


def stage_blockers(ctx, project):
    """Reasons the current stage can't be completed yet.

    - every unticked '- [ ]' item in the stage's Markdown files;
    - the stage folder, or a checklist file the stage's template provides,
      is missing (deleting it must not skip the gate);
    - a checklist file whose template has a checklist no longer has any items.
    """
    stage = ctx.config.stage(project.stage)
    stage_dir = project.folder / stage["folder"]
    if not stage_dir.is_dir():
        return [f"stage folder {stage['folder']}/ is missing. Restore it (e.g. git checkout -- "
                f"\"{project.folder.name}/{stage['folder']}\") or use --force"]
    blockers = []
    brand, language = project.meta.get("brand"), project.language
    for name in (t for t in stage["templates"] if t.endswith(".md")):
        if not (stage_dir / name).is_file():
            blockers.append(f"{name}: file is missing. Restore it or use --force")
            continue
        text = read_text(stage_dir / name)
        template_text = read_text(find_template(ctx.paths, name, brand, language))
        if has_checklist(template_text) and not has_checklist(text):
            blockers.append(f"{name}: the stage checklist was removed. Restore it or use --force")
    for md in sorted(stage_dir.glob("*.md")):
        blockers += [f"{md.name}: {item}" for item in unchecked_items(read_text(md))]
    return blockers


def gate_problems(ctx, project):
    """Everything that stops the current stage from completing:
    (unticked/missing checklist items, FAIL findings from automated checks)."""
    return stage_blockers(ctx, project), failures(run_checks(ctx, project))


def advance(ctx, project, force=False, day=None):
    stages = ctx.config.stages
    index = ctx.config.stage_index(project.stage)
    if index == len(stages) - 1:
        raise FactoryError("Project is already at the last stage (Analytics).")
    blockers, fails = gate_problems(ctx, project)
    if (blockers or fails) and not force:
        parts = []
        if blockers:
            parts.append("Stage checklist not complete:\n  - " + "\n  - ".join(blockers))
        if fails:
            parts.append("Automated checks failed:\n  - " + "\n  - ".join(format_finding(f) for f in fails))
        fix = "Tick the boxes" if not fails else ("Fix the FAIL findings" if not blockers
                                                   else "Tick the boxes and fix the FAIL findings")
        raise FactoryError("\n".join(parts) + f"\n{fix} (details: python -m factory check {project.id}), "
                           "or use --force.")
    new_stage = stages[index + 1]["id"]
    project.meta["stage"] = new_stage
    entry = {"stage": new_stage, "date": day or today()}
    if blockers or fails:
        entry["forced"] = True
    if fails:
        entry["forced_findings"] = sorted({f.code for f in fails})
    project.meta["history"].append(entry)
    project.save()
    return new_stage


def back(ctx, project, day=None):
    """Move a project back one stage (e.g. to fix the script after QC).
    Nothing in the project folder is changed; the step is recorded in history."""
    index = ctx.config.stage_index(project.stage)
    if index == 0:
        raise FactoryError("Project is already at the first stage (Research).")
    previous = ctx.config.stages[index - 1]["id"]
    project.meta["history"].append({"stage": previous, "date": day or today(), "back_from": project.stage})
    project.meta["stage"] = previous
    project.save()
    return previous


# ---------------------------------------------------------------- commands

def check_idea_language(ctx, idea, idea_language, requested):
    """An idea belongs to one language backlog, so --lang can't change it."""
    if requested is None or requested == idea_language:
        return
    have = ctx.config.languages[idea_language]["name"]
    want = ctx.config.languages[requested]["name"]
    raise FactoryError(
        f"Conflicting options: idea {idea['id']} is in the {have} backlog ({idea_language}), "
        f"but --lang {requested} ({want}) was given.\n"
        f"  - To create the {have} project, drop --lang:\n"
        f"      python -m factory new --idea {idea['id']}\n"
        f"  - To make a {want} version, add it to the {want} backlog first:\n"
        f"      python -m factory ideas add \"<{want} title>\" --lang {requested} "
        f"--division {idea['division']} --format {idea['format']}")


def cmd_new(args, ctx):
    brand = brand_id(args, ctx)
    title, language, division, fmt = args.title, args.lang, args.division, args.format
    if args.idea:
        language, idea = ideas_mod.find_idea(ctx, brand, args.idea)
        check_idea_language(ctx, idea, language, args.lang)
        if idea["project_id"]:
            hint = ""
            if ideas_mod.linked_project_missing(ctx, brand, idea):
                hint = (f". That project no longer exists; if it was deleted, run: "
                        f"python -m factory ideas unlink {idea['id']}")
            raise FactoryError(f"Idea {idea['id']} already has project {idea['project_id']}{hint}")
        title = title or idea["title"]
        division = division or idea["division"]
        fmt = fmt or idea["format"]
    if not (title and language and division):
        raise FactoryError("Give a title with --lang and --division, or use --idea IDEA-ID")
    project = create_project(ctx, title, language, division, fmt or "short", brand=brand,
                             seconds=args.seconds, idea_id=args.idea or "")
    print(f"Created: {display_path(project.folder, ctx.paths.root)}")
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
    print(f"  Folder   : {display_path(p.folder, ctx.paths.root)}")
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
    findings = run_checks(ctx, p)
    if findings:
        fails = sum(f.level == FAIL for f in findings)
        warns = sum(f.level == WARN for f in findings)
        print(f"  Automated checks: {fails} FAIL, {warns} WARN (details: python -m factory check {p.id})")
    for pub in m.get("publications", []):
        print(f"  Published: {pub['platform']} {pub['date']} {pub['url']}")
    return 0


def cmd_check(args, ctx):
    p = find_project(ctx, args.project)
    stages = [s["id"] for s in ctx.config.stages] if args.all else [args.stage or p.stage]
    any_fail = False
    for stage_id in stages:
        label = ctx.config.stage(stage_id)["label"]
        findings = run_checks(ctx, p, stage_id)
        current = stage_id == p.stage
        blockers = stage_blockers(ctx, p) if current else []
        if args.all and not findings and not blockers:
            continue
        print(f"{label}{' (current stage)' if current else ''}:")
        for item in blockers:
            print(f"  CHECKLIST {item}")
        for f in findings:
            print(f"  {format_finding(f)}")
        if not findings and not blockers:
            print("  no problems found")
        any_fail = any_fail or bool(failures(findings)) or bool(blockers)
    if args.all and not any_fail:
        print("No FAIL findings in any stage.")
    return 1 if any_fail else 0


def cmd_migrate(args, ctx):
    brand = brand_id(args, ctx)
    results = migrate_mod.apply(ctx, brand) if args.apply else migrate_mod.plan(ctx, brand)
    if not results:
        print(f"All projects are up to date (format {CURRENT_SCHEMA}).")
        return 0
    verb = "Upgraded" if args.apply else "Would upgrade"
    for project, version, actions in results:
        print(f"{verb} {project.id} (format {version} → {CURRENT_SCHEMA}):")
        for action in actions:
            print(f"  - {action}")
    if not args.apply:
        print("Preview only: nothing was changed. Run again with --apply to upgrade. "
              "Existing files are never overwritten.")
    return 0


def cmd_back(args, ctx):
    p = find_project(ctx, args.project)
    old = p.stage
    new_stage = back(ctx, p)
    print(f"{p.id}: {ctx.config.stage(old)['label']} → back to {ctx.config.stage(new_stage)['label']}")
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
    new.add_argument("--idea", help="create from an idea ID, e.g. EN-002. The language comes from the "
                                    "idea (--lang must match it); a title, --division or --format you "
                                    "give replaces the idea's value")
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
    ad.add_argument("--force", action="store_true",
                    help="advance even with unticked checklist items or FAIL findings (recorded)")
    ad.set_defaults(func=cmd_advance)

    ck = sub.add_parser("check", help="Production Manager: automated checks and checklist for a project")
    ck.add_argument("project")
    ck.add_argument("--stage", help="check another stage instead of the current one")
    ck.add_argument("--all", action="store_true", help="check every stage")
    ck.set_defaults(func=cmd_check)

    bk = sub.add_parser("back", help="Production Manager: move a project back one stage (recorded)")
    bk.add_argument("project")
    bk.set_defaults(func=cmd_back)

    mg = sub.add_parser("migrate", help="Production Manager: upgrade older projects to the current format")
    add_brand(mg)
    mg.add_argument("--apply", action="store_true", help="make the changes (default: preview only)")
    mg.set_defaults(func=cmd_migrate)
