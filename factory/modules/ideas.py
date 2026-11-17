"""Module 3: Idea Manager. Per-language idea backlogs (brands/<brand>/<lang>/ideas.csv).

The CSV files may be edited in Excel; see core/files.py for how that is handled.
"""

import re

from factory.core.config import FactoryError
from factory.core.files import append_csv, read_csv_table, require_columns, to_float, today, write_csv
from factory.core.options import (add_brand, add_division, add_language, brand_id,
                                  check_division, check_format, check_language)

FIELDS = ["id", "title", "division", "format", "demand", "competition", "effort",
          "score", "status", "project_id", "created"]
REQUIRED = ["id", "title", "division", "format", "status", "project_id"]


def score(demand, competition, effort):
    """1.0–5.0. Demand counts double; low competition and low effort are better."""
    return round((demand * 2 + (6 - competition) + (6 - effort)) / 4, 1)


def load_ideas(ctx, brand, language):
    path = ctx.paths.ideas_csv(brand, language)
    header, rows = read_csv_table(path)
    if header:
        require_columns(path, header, REQUIRED)
    return [r for r in rows if r.get("id")]  # rows without an ID are ignored


def idea_number(idea_id, prefix):
    """EN-007 → 7. Returns None for IDs that don't follow the pattern."""
    m = re.fullmatch(rf"{prefix}-(\d+)", idea_id.strip(), re.IGNORECASE)
    return int(m.group(1)) if m else None


def find_idea(ctx, brand, idea_id):
    """Return (language, idea). Searches every language backlog of the brand."""
    for language in ctx.config.languages:
        for idea in load_ideas(ctx, brand, language):
            if idea["id"].lower() == idea_id.lower():
                return language, idea
    raise FactoryError(f"Idea '{idea_id}' not found for brand '{brand}'")


def add_idea(ctx, brand, language, title, division, fmt, demand, competition, effort):
    check_language(ctx, language)
    check_division(ctx, division, brand)
    check_format(ctx, fmt)
    for value in (demand, competition, effort):
        if not 1 <= value <= 5:
            raise FactoryError("demand, competition and effort must be 1–5")
    ideas = load_ideas(ctx, brand, language)
    prefix = language.upper()
    numbers = [n for n in (idea_number(i["id"], prefix) for i in ideas) if n is not None]
    idea = {
        "id": f"{prefix}-{max(numbers, default=0) + 1:03d}", "title": title, "division": division,
        "format": fmt, "demand": demand, "competition": competition, "effort": effort,
        "score": score(demand, competition, effort), "status": "backlog", "project_id": "",
        "created": today(),
    }
    append_csv(ctx.paths.ideas_csv(brand, language), idea, FIELDS)
    return idea


def link_project(ctx, brand, language, idea_id, project_id):
    path = ctx.paths.ideas_csv(brand, language)
    ideas = load_ideas(ctx, brand, language)
    for idea in ideas:
        if idea["id"] == idea_id:
            idea["status"] = "in_production"
            idea["project_id"] = project_id
    write_csv(path, ideas, FIELDS)


def project_folder_names(ctx, brand):
    """Names of every project folder in the brand, valid or damaged."""
    return {p.name for p in ctx.paths.brand_dir(brand).glob("*/*/*") if p.is_dir()}


def linked_project_missing(ctx, brand, idea, folder_names=None):
    """True if the idea points to a project that no longer exists anywhere."""
    project_id = idea.get("project_id", "").strip()
    if not project_id:
        return False
    names = project_folder_names(ctx, brand) if folder_names is None else folder_names
    return project_id not in names


def unlink_idea(ctx, brand, idea_id):
    """Put an idea back in the backlog after its project was deleted.

    Refused if the project (or any folder with its ID, even a damaged one)
    still exists, so a working project can never lose its idea link. Only
    this idea's 'status' and 'project_id' change; other rows and columns are
    kept. Returns (language, idea_id, old_project_id, old_status)."""
    language, idea = find_idea(ctx, brand, idea_id)
    old_project = idea["project_id"].strip()
    if not old_project:
        raise FactoryError(f"Idea {idea['id']} is not linked to a project (status: {idea['status']})")
    if not linked_project_missing(ctx, brand, idea):
        raise FactoryError(f"Idea {idea['id']} is linked to {old_project}, which still exists. "
                           "Unlinking is only allowed after the project folder has been deleted.")
    path = ctx.paths.ideas_csv(brand, language)
    ideas = load_ideas(ctx, brand, language)
    for row in ideas:
        if row["id"].lower() == idea["id"].lower() and row["project_id"].strip() == old_project:
            row["status"] = "backlog"
            row["project_id"] = ""
    write_csv(path, ideas, FIELDS)
    return language, idea["id"], old_project, idea["status"]


def cmd_list(args, ctx):
    brand = brand_id(args, ctx)
    languages = [check_language(ctx, args.lang)] if getattr(args, "lang", None) else list(ctx.config.languages)
    for language in languages:
        ideas = load_ideas(ctx, brand, language)
        if getattr(args, "division", None):
            ideas = [i for i in ideas if i["division"] == args.division]
        print(f"== {ctx.config.languages[language]['name']} ({len(ideas)} ideas) ==")
        folders = project_folder_names(ctx, brand)
        for i in sorted(ideas, key=lambda i: to_float(i.get("score")), reverse=True):
            print(f"  {i['id']:<7} {i.get('score', ''):>4}  {i['status']:<14} {i['division']:<18} {i['format']:<5} {i['title']}")
            if linked_project_missing(ctx, brand, i, folders):
                print(f"          ⚠ linked project {i['project_id']} not found. If it was deleted, run: "
                      f"python -m factory ideas unlink {i['id']}")
    return 0


def cmd_unlink(args, ctx):
    language, idea_id, old_project, old_status = unlink_idea(ctx, brand_id(args, ctx), args.idea)
    print(f"Unlinked {idea_id} from deleted project {old_project}; status {old_status} → backlog.")
    print(f"(To undo, set project_id back to {old_project} in "
          f"brands/{brand_id(args, ctx)}/{language}/ideas.csv)")
    return 0


def cmd_add(args, ctx):
    idea = add_idea(ctx, brand_id(args, ctx), args.lang, args.title, args.division, args.format,
                    args.demand, args.competition, args.effort)
    print(f"Added {idea['id']} (score {idea['score']}): {idea['title']}")
    return 0


def register(sub):
    p = sub.add_parser("ideas", help="Idea Manager: list and add ideas")
    add_brand(p)
    add_language(p)
    add_division(p)
    p.set_defaults(func=cmd_list)
    s = p.add_subparsers(metavar="action")
    ls = s.add_parser("list", help="list ideas by score")
    add_brand(ls)
    add_language(ls)
    add_division(ls)
    ls.set_defaults(func=cmd_list)
    ad = s.add_parser("add", help="add an idea to a language backlog")
    ad.add_argument("title")
    add_brand(ad)
    add_language(ad, required=True)
    add_division(ad, required=True)
    ad.add_argument("--format", default="short", help="short or long")
    for name in ("demand", "competition", "effort"):
        ad.add_argument(f"--{name}", type=int, default=3, help="1–5")
    ad.set_defaults(func=cmd_add)
    un = s.add_parser("unlink", help="return an idea to the backlog after its project was deleted")
    un.add_argument("idea", help="idea ID, e.g. EN-002")
    add_brand(un)
    un.set_defaults(func=cmd_unlink)
