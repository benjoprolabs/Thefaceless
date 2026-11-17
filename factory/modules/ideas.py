"""Module 3: Idea Manager. Per-language idea backlogs (brands/<brand>/<lang>/ideas.csv).

The CSV files may be edited in Excel; see core/files.py for how that is handled.

Idea life cycle (M1, v0.4.1):

    backlog ⇄ shortlisted ──(new --idea)──▶ in_production ──(first publication)──▶ published
       │           │
       └─▶ rejected / archived (and back to backlog)

`in_production` and `published` are set by the system: `new --idea` links an
idea to its new project, and recording the project's first publication marks
the idea published. Ideas that have a project can't be changed by hand (the
project link stays safe); `ideas unlink` returns an idea to the backlog only
after its project folder was deleted.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from factory.core.checks import WARN, Finding, register
from factory.core.config import FactoryError
from factory.core.files import append_csv, read_csv_table, require_columns, to_float, today, write_csv
from factory.core.options import (add_brand, add_division, add_language, brand_id,
                                  check_division, check_format, check_language)
from factory.core.projects import iter_projects

FIELDS = ["id", "title", "division", "format", "demand", "competition", "effort",
          "score", "status", "project_id", "created", "tags", "notes", "updated"]
REQUIRED = ["id", "title", "division", "format", "status", "project_id"]

STATUSES = ("backlog", "shortlisted", "in_production", "published", "rejected", "archived")
SYSTEM_STATUSES = ("in_production", "published")
# Changes a user may make with `ideas status` (decision 1). Ideas with a
# project (in_production, published) have no manual changes, except the
# special case of marking an idea published once its project has a
# recorded publication (see set_status).
MANUAL_TRANSITIONS = {
    "backlog": ("shortlisted", "rejected", "archived"),
    "shortlisted": ("backlog", "rejected", "archived"),
    "rejected": ("backlog", "archived"),
    "archived": ("backlog",),
    "in_production": (),
    "published": (),
}
PRODUCIBLE = ("backlog", "shortlisted")  # statuses `new --idea` accepts (decision 2)
DEFAULT_DUPLICATE_THRESHOLD = 0.85


def score(demand, competition, effort):
    """1.0–5.0. Demand counts double; low competition and low effort are better."""
    return round((demand * 2 + (6 - competition) + (6 - effort)) / 4, 1)


def normalise_status(value):
    """'In Production', 'in-production' → 'in_production'."""
    return re.sub(r"[\s-]+", "_", (value or "").strip().lower())


def load_ideas(ctx, brand, language):
    path = ctx.paths.ideas_csv(brand, language)
    header, rows = read_csv_table(path)
    if header:
        require_columns(path, header, REQUIRED)
    ideas = [r for r in rows if r.get("id")]  # rows without an ID are ignored
    for idea in ideas:  # files from before v0.4.1 have no tags/notes/updated
        for column in ("tags", "notes", "updated"):
            idea.setdefault(column, "")
    return ideas


def save_ideas(ctx, brand, language, ideas):
    write_csv(ctx.paths.ideas_csv(brand, language), ideas, FIELDS)


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


def _update_row(ctx, brand, language, idea_id, changes):
    """Apply `changes` to one idea (matched case-insensitively), set 'updated'
    and save. Every other row and column (including user columns) is kept."""
    ideas = load_ideas(ctx, brand, language)
    found = False
    for row in ideas:
        if row["id"].lower() == idea_id.lower():
            row.update(changes)
            row["updated"] = today()
            found = True
    if not found:
        raise FactoryError(f"Idea '{idea_id}' not found in the {language} idea list")
    save_ideas(ctx, brand, language, ideas)


def check_scores(demand, competition, effort):
    for value in (demand, competition, effort):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise FactoryError("demand, competition and effort must be whole numbers from 1 to 5")


def add_idea(ctx, brand, language, title, division, fmt, demand, competition, effort):
    check_language(ctx, language)
    check_division(ctx, division, brand)
    check_format(ctx, fmt)
    check_scores(demand, competition, effort)
    if not title.strip():
        raise FactoryError("The title can't be empty")
    ideas = load_ideas(ctx, brand, language)
    prefix = language.upper()
    numbers = [n for n in (idea_number(i["id"], prefix) for i in ideas) if n is not None]
    idea = {
        "id": f"{prefix}-{max(numbers, default=0) + 1:03d}", "title": title.strip(), "division": division,
        "format": fmt, "demand": demand, "competition": competition, "effort": effort,
        "score": score(demand, competition, effort), "status": "backlog", "project_id": "",
        "created": today(), "tags": "", "notes": "", "updated": "",
    }
    append_csv(ctx.paths.ideas_csv(brand, language), idea, FIELDS)
    return idea


def check_producible(ctx, brand, language, idea_id):
    """An idea can become a project only from backlog or shortlisted (decision 2)."""
    for idea in load_ideas(ctx, brand, language):
        if idea["id"].lower() == idea_id.lower():
            break
    else:
        raise FactoryError(f"Idea '{idea_id}' not found in the {ctx.config.languages[language]['name']} idea list")
    if idea["project_id"].strip():
        raise FactoryError(f"Idea {idea['id']} already has project {idea['project_id']}")
    status = normalise_status(idea["status"])
    if status not in PRODUCIBLE:
        raise FactoryError(f"Idea {idea['id']} is '{idea['status']}'. Only backlog or shortlisted ideas can "
                           f"become projects. To restore it: python -m factory ideas status {idea['id']} backlog")
    return idea


def link_project(ctx, brand, language, idea_id, project_id):
    _update_row(ctx, brand, language, idea_id, {"status": "in_production", "project_id": project_id})


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
    this idea's 'status', 'project_id' and 'updated' change; other rows and
    columns are kept. Returns (language, idea_id, old_project_id, old_status)."""
    language, idea = find_idea(ctx, brand, idea_id)
    old_project = idea["project_id"].strip()
    if not old_project:
        raise FactoryError(f"Idea {idea['id']} is not linked to a project (status: {idea['status']})")
    if not linked_project_missing(ctx, brand, idea):
        raise FactoryError(f"Idea {idea['id']} is linked to {old_project}, which still exists. "
                           "Unlinking is only allowed after the project folder has been deleted.")
    ideas = load_ideas(ctx, brand, language)
    for row in ideas:
        if row["id"].lower() == idea["id"].lower() and row["project_id"].strip() == old_project:
            row.update(status="backlog", project_id="", updated=today())
    save_ideas(ctx, brand, language, ideas)
    return language, idea["id"], old_project, idea["status"]


# ---------------------------------------------------------------- statuses

def projects_by_id(ctx, brand):
    return {p.id: p for p in iter_projects(ctx, brand=brand)}


def set_status(ctx, brand, idea_id, new_status):
    """Change an idea's status by hand, following MANUAL_TRANSITIONS.

    Marking an idea `published` by hand is allowed only when it's linked to
    an existing project that has at least one recorded publication (used to
    correct older data). `in_production` is never set by hand."""
    language, idea = find_idea(ctx, brand, idea_id)
    new = normalise_status(new_status)
    if new not in STATUSES:
        raise FactoryError(f"Unknown status '{new_status}'. Use one of: {', '.join(STATUSES)}")
    current = normalise_status(idea["status"])
    if new == current:
        raise FactoryError(f"Idea {idea['id']} is already '{current}'")
    project_id = idea["project_id"].strip()
    if new == "in_production":
        raise FactoryError("'in_production' is set automatically when a project is created: "
                           f"python -m factory new --idea {idea['id']}")
    if new == "published":
        project = projects_by_id(ctx, brand).get(project_id) if project_id else None
        if project is None or not project.meta.get("publications"):
            raise FactoryError(f"Idea {idea['id']} can be marked published only when its project has a "
                               "recorded publication (python -m factory publish record ...)")
    elif current in SYSTEM_STATUSES or project_id:
        raise FactoryError(f"Idea {idea['id']} is '{current}' with project {project_id or '(none)'}; its "
                           "status can't be changed by hand, so the project link stays safe. If the "
                           f"project was deleted, run: python -m factory ideas unlink {idea['id']}")
    else:
        # an unknown status (e.g. a typo made in Excel) may be repaired to any
        # status that can normally be set by hand
        if current in STATUSES:
            allowed = MANUAL_TRANSITIONS[current]
        else:
            allowed = ("backlog", "shortlisted", "rejected", "archived")
        if new not in allowed:
            raise FactoryError(f"Idea {idea['id']} can't change from '{current}' to '{new}'. "
                               f"Allowed: {', '.join(allowed) or 'none'}")
    _update_row(ctx, brand, language, idea["id"], {"status": new})
    return language, idea["id"], current, new


def mark_published(ctx, project):
    """Called after a publication is recorded: in_production → published.

    Returns a message, or None if nothing changed. Raises FactoryError or
    OSError if the idea list can't be updated (the caller turns that into a
    warning; the publication itself is already saved)."""
    idea_id = (project.meta.get("idea_id") or "").strip()
    if not idea_id or not project.meta.get("publications"):
        return None
    brand = project.meta.get("brand") or ctx.config.settings["default_brand"]
    idea = next((i for i in load_ideas(ctx, brand, project.language) if i["id"].lower() == idea_id.lower()), None)
    if idea is None:
        raise FactoryError(f"idea {idea_id} was not found in the {project.language} idea list")
    if idea["project_id"].strip() != project.id:
        raise FactoryError(f"idea {idea_id} is not linked to {project.id}")
    status = normalise_status(idea["status"])
    if status == "published":
        return None
    if status != "in_production":
        raise FactoryError(f"idea {idea_id} has status '{idea['status']}', expected in_production")
    _update_row(ctx, brand, project.language, idea["id"], {"status": "published"})
    return f"Idea {idea['id']} marked published."


# ---------------------------------------------------------------- tags, edit

def normalise_tags(text):
    """'Space, AI ,space' → 'space, ai'. Comma-separated; any script allowed."""
    tags = []
    for tag in (text or "").split(","):
        tag = re.sub(r"\s+", " ", tag).strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return ", ".join(tags)


def tag_list(idea):
    return [t for t in normalise_tags(idea.get("tags", "")).split(", ") if t]


def edit_idea(ctx, brand, idea_id, title=None, division=None, fmt=None, demand=None,
              competition=None, effort=None, tags=None, notes=None):
    """Edit an idea. Division and format are locked while the idea has a
    project (decision 5). Returns (language, idea_id, {field: (old, new)})."""
    language, idea = find_idea(ctx, brand, idea_id)
    linked = bool(idea["project_id"].strip())
    if linked and (division is not None or fmt is not None):
        raise FactoryError(f"Idea {idea['id']} has project {idea['project_id']}: its division and format "
                           "can't change, because the project's folder and length limits depend on them. "
                           "Title, scores, tags and notes can still be edited.")
    changes = {}
    if title is not None:
        if not title.strip():
            raise FactoryError("The title can't be empty")
        changes["title"] = title.strip()
    if division is not None:
        changes["division"] = check_division(ctx, division.strip().lower(), brand)
    if fmt is not None:
        changes["format"] = check_format(ctx, fmt.strip().lower())
    if any(v is not None for v in (demand, competition, effort)):
        values = []
        for name, new in (("demand", demand), ("competition", competition), ("effort", effort)):
            if new is None:
                try:
                    new = int(to_float(idea.get(name), default=-1))
                except (TypeError, ValueError):
                    new = -1
                if new == -1:
                    raise FactoryError(f"Idea {idea['id']} has no valid '{name}' value; set it with --{name}")
            values.append(new)
        check_scores(*values)
        changes.update(demand=values[0], competition=values[1], effort=values[2], score=score(*values))
    if tags is not None:
        changes["tags"] = normalise_tags(tags)
    if notes is not None:
        changes["notes"] = re.sub(r"\s*[\r\n]+\s*", " ", notes).strip()
    if not changes:
        raise FactoryError("Nothing to change. Use --title, --division, --format, --demand, "
                           "--competition, --effort, --tags or --notes")
    diff = {k: (str(idea.get(k, "")), str(v)) for k, v in changes.items() if str(idea.get(k, "")) != str(v)}
    if not diff:
        raise FactoryError(f"Idea {idea['id']} already has these values")
    _update_row(ctx, brand, language, idea["id"], changes)
    return language, idea["id"], diff


# ---------------------------------------------------------------- duplicates

def normalise_title(title):
    """For comparison only: case, accents and punctuation ignored; letters of
    every script (including Jawi) kept."""
    decomposed = unicodedata.normalize("NFKD", title.casefold())
    kept = [c if unicodedata.category(c)[0] in "LN" else " "
            for c in decomposed if not unicodedata.combining(c)]
    return " ".join("".join(kept).split())


def duplicate_threshold(ctx):
    value = ctx.config.rules.get("ideas", {}).get("duplicate_threshold", DEFAULT_DUPLICATE_THRESHOLD)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
        raise FactoryError("config/rules.json: ideas.duplicate_threshold must be a number above 0 and up to 1")
    return float(value)


def similarity(a, b):
    a, b = normalise_title(a), normalise_title(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def similar_ideas(ctx, brand, language, title, exclude_id=None):
    """[(similarity, idea)] for ideas in the same language at or above the threshold."""
    threshold = duplicate_threshold(ctx)
    matches = []
    for idea in load_ideas(ctx, brand, language):
        if exclude_id and idea["id"].lower() == exclude_id.lower():
            continue
        ratio = similarity(title, idea["title"])
        if ratio >= threshold:
            matches.append((round(ratio, 2), idea))
    return sorted(matches, key=lambda m: -m[0])


def duplicate_pairs(ctx, brand, language):
    threshold = duplicate_threshold(ctx)
    ideas = load_ideas(ctx, brand, language)
    pairs = []
    for i, a in enumerate(ideas):
        for b in ideas[i + 1:]:
            ratio = similarity(a["title"], b["title"])
            if ratio >= threshold:
                pairs.append((round(ratio, 2), a, b))
    return sorted(pairs, key=lambda p: -p[0])


# ---------------------------------------------------------------- consistency

def check_ideas(ctx, brand, language=None):
    """Consistency problems in the idea lists: [(language, idea_id, problem)].
    Read-only (decision 4)."""
    projects = projects_by_id(ctx, brand)
    folders = project_folder_names(ctx, brand)
    enabled = ctx.config.brand(brand)["divisions"]
    problems = []
    for lang in [language] if language else list(ctx.config.languages):
        seen = {}
        for idea in load_ideas(ctx, brand, lang):
            iid, status = idea["id"], normalise_status(idea["status"])
            project_id = idea["project_id"].strip()

            def add(problem):
                problems.append((lang, iid, problem))
            key = iid.lower()
            if key in seen:
                add("duplicate idea ID (appears more than once in the list)")
            seen[key] = True
            if status not in STATUSES:
                add(f"unknown status '{idea['status']}' (use one of: {', '.join(STATUSES)})")
            if idea["division"] not in ctx.config.divisions:
                add(f"unknown division '{idea['division']}'")
            elif idea["division"] not in enabled:
                add(f"division '{idea['division']}' is not enabled for brand '{brand}'")
            if idea["format"] not in ctx.config.formats:
                add(f"unknown format '{idea['format']}'")
            for name in ("demand", "competition", "effort"):
                value = to_float(idea.get(name), default=-1)
                if not (1 <= value <= 5 and float(value).is_integer()):  # NaN/inf fail too
                    add(f"{name} must be a whole number from 1 to 5 (found '{idea.get(name, '')}')")
            if status == "in_production" and not project_id:
                add("status is in_production but no project is linked")
            if status in ("backlog", "shortlisted", "rejected", "archived") and project_id:
                add(f"status is {status} but it is linked to project {project_id}")
            if project_id and project_id not in folders:
                add(f"linked project {project_id} not found. If it was deleted: "
                    f"python -m factory ideas unlink {iid}")
                continue
            project = projects.get(project_id)
            published = bool(project and project.meta.get("publications"))
            if status == "published" and not project_id:
                add("status is published but no project is linked")
            elif status == "published" and project is not None and not published:
                add(f"status is published but project {project_id} has no recorded publication")
            if status == "in_production" and published:
                add(f"project {project_id} has been published; run: python -m factory ideas status {iid} published")
    return problems


@register("research")
def check_project_idea_link(ctx, project):
    """Project side (decision 4): WARN only, never blocks a stage."""
    idea_id = (project.meta.get("idea_id") or "").strip()
    if not idea_id:
        return []
    brand = project.meta.get("brand") or ctx.config.settings["default_brand"]
    idea = next((i for i in load_ideas(ctx, brand, project.language) if i["id"].lower() == idea_id.lower()), None)
    if idea is None:
        return [Finding(WARN, "IDEA_MISSING", f"linked idea {idea_id} is not in the "
                        f"{ctx.config.languages[project.language]['name']} idea list", "project.json")]
    if idea["project_id"].strip() != project.id:
        linked = idea["project_id"].strip() or "no project"
        return [Finding(WARN, "IDEA_NOT_LINKED", f"idea {idea_id} is linked to {linked}, not to this project",
                        "project.json")]
    return []


# ---------------------------------------------------------------- commands

def _ideas_for(args, ctx, brand):
    languages = [check_language(ctx, args.lang)] if getattr(args, "lang", None) else list(ctx.config.languages)
    return [(language, load_ideas(ctx, brand, language)) for language in languages]


def cmd_list(args, ctx):
    brand = brand_id(args, ctx)
    status_filter = normalise_status(getattr(args, "status", None)) if getattr(args, "status", None) else None
    if status_filter and status_filter not in STATUSES:
        raise FactoryError(f"Unknown status '{args.status}'. Use one of: {', '.join(STATUSES)}")
    tag_filter = normalise_tags(getattr(args, "tag", None) or "") or None
    folders = project_folder_names(ctx, brand)
    for language, ideas in _ideas_for(args, ctx, brand):
        if getattr(args, "division", None):
            ideas = [i for i in ideas if i["division"] == args.division]
        if status_filter:
            ideas = [i for i in ideas if normalise_status(i["status"]) == status_filter]
        if tag_filter:
            ideas = [i for i in ideas if tag_filter in tag_list(i)]
        print(f"== {ctx.config.languages[language]['name']} ({len(ideas)} ideas) ==")
        for i in sorted(ideas, key=lambda i: to_float(i.get("score")), reverse=True):
            tags = f"  [{i['tags']}]" if i.get("tags") else ""
            print(f"  {i['id']:<7} {i.get('score', ''):>4}  {i['status']:<14} {i['division']:<18} "
                  f"{i['format']:<5} {i['title']}{tags}")
            if linked_project_missing(ctx, brand, i, folders):
                print(f"          ⚠ linked project {i['project_id']} not found. If it was deleted, run: "
                      f"python -m factory ideas unlink {i['id']}")
    return 0


def cmd_show(args, ctx):
    brand = brand_id(args, ctx)
    language, i = find_idea(ctx, brand, args.idea)
    print(f"{i['id']}  {i['title']}")
    print(f"  Language : {ctx.config.languages[language]['name']}   Division: {i['division']}   Format: {i['format']}")
    print(f"  Status   : {i['status']}   Score: {i.get('score', '')} (demand {i.get('demand', '')}, "
          f"competition {i.get('competition', '')}, effort {i.get('effort', '')})")
    print(f"  Tags     : {i.get('tags') or '-'}")
    print(f"  Notes    : {i.get('notes') or '-'}")
    print(f"  Created  : {i.get('created') or '-'}   Updated: {i.get('updated') or '-'}")
    project_id = i["project_id"].strip()
    if project_id:
        project = projects_by_id(ctx, brand).get(project_id)
        if project is not None:
            stage = ctx.config.stage(project.stage)["label"]
            print(f"  Project  : {project_id} (stage: {stage}, publications: {len(project.meta.get('publications', []))})")
        elif linked_project_missing(ctx, brand, i):
            print(f"  Project  : {project_id} ⚠ not found (python -m factory ideas unlink {i['id']})")
        else:
            print(f"  Project  : {project_id} ⚠ can't be read (see: python -m factory status)")
    else:
        print("  Project  : -")
    for ratio, other in similar_ideas(ctx, brand, language, i["title"], exclude_id=i["id"]):
        print(f"  Possible duplicate: {other['id']} ({ratio:.2f}) {other['title']}")
    return 0


def cmd_status(args, ctx):
    language, idea_id, old, new = set_status(ctx, brand_id(args, ctx), args.idea, args.status)
    print(f"{idea_id}: {old} → {new}")
    return 0


def cmd_edit(args, ctx):
    language, idea_id, diff = edit_idea(
        ctx, brand_id(args, ctx), args.idea, title=args.title, division=args.division, fmt=args.format,
        demand=args.demand, competition=args.competition, effort=args.effort, tags=args.tags, notes=args.notes)
    print(f"Updated {idea_id}:")
    for field, (old, new) in diff.items():
        print(f"  {field}: {old or '-'} → {new or '-'}")
    return 0


def cmd_dupes(args, ctx):
    brand = brand_id(args, ctx)
    threshold = duplicate_threshold(ctx)
    found = 0
    for language, _ in _ideas_for(args, ctx, brand):
        pairs = duplicate_pairs(ctx, brand, language)
        if not pairs:
            continue
        print(f"== {ctx.config.languages[language]['name']} ==")
        for ratio, a, b in pairs:
            print(f"  {ratio:.2f}  {a['id']} {a['title']}")
            print(f"        {b['id']} {b['title']}")
        found += len(pairs)
    print(f"{found} possible duplicate pair(s) (similarity ≥ {threshold:.2f}; change it in config/rules.json).")
    return 0


def cmd_check(args, ctx):
    problems = check_ideas(ctx, brand_id(args, ctx), getattr(args, "lang", None))
    for language, idea_id, problem in problems:
        print(f"  {language.upper()} {idea_id}: {problem}")
    print("Idea lists are consistent." if not problems else f"{len(problems)} problem(s) found.")
    return 1 if problems else 0


def cmd_unlink(args, ctx):
    language, idea_id, old_project, old_status = unlink_idea(ctx, brand_id(args, ctx), args.idea)
    print(f"Unlinked {idea_id} from deleted project {old_project}; status {old_status} → backlog.")
    print(f"(To undo, set project_id back to {old_project} in "
          f"brands/{brand_id(args, ctx)}/{language}/ideas.csv)")
    return 0


def cmd_add(args, ctx):
    brand = brand_id(args, ctx)
    matches = similar_ideas(ctx, brand, args.lang, args.title)
    idea = add_idea(ctx, brand, args.lang, args.title, args.division, args.format,
                    args.demand, args.competition, args.effort)
    print(f"Added {idea['id']} (score {idea['score']}): {idea['title']}")
    for ratio, other in matches:
        ctx.warnings[f"dupe:{idea['id']}:{other['id']}"] = (
            f"{idea['id']} looks like a duplicate of {other['id']} ({ratio:.2f}): {other['title']}")
    return 0


def register(sub):
    p = sub.add_parser("ideas", help="Idea Manager: list, add, edit and check ideas")
    add_brand(p)
    add_language(p)
    add_division(p)
    p.add_argument("--status", help="only ideas with this status")
    p.add_argument("--tag", help="only ideas with this tag")
    p.set_defaults(func=cmd_list)
    s = p.add_subparsers(metavar="action")

    ls = s.add_parser("list", help="list ideas by score")
    add_brand(ls)
    add_language(ls)
    add_division(ls)
    ls.add_argument("--status", help=f"only ideas with this status ({', '.join(STATUSES)})")
    ls.add_argument("--tag", help="only ideas with this tag")
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

    sh = s.add_parser("show", help="all details of one idea")
    sh.add_argument("idea", help="idea ID, e.g. EN-002")
    add_brand(sh)
    sh.set_defaults(func=cmd_show)

    ed = s.add_parser("edit", help="edit an idea (division/format locked once it has a project)")
    ed.add_argument("idea", help="idea ID, e.g. EN-002")
    add_brand(ed)
    ed.add_argument("--title")
    ed.add_argument("--division")
    ed.add_argument("--format", help="short or long")
    for name in ("demand", "competition", "effort"):
        ed.add_argument(f"--{name}", type=int, help="1–5")
    ed.add_argument("--tags", help='comma-separated, e.g. "space, ocean" (empty "" clears)')
    ed.add_argument("--notes", help='free text (empty "" clears)')
    ed.set_defaults(func=cmd_edit)

    st = s.add_parser("status", help="change an idea's status (backlog, shortlisted, rejected, archived, published)")
    st.add_argument("idea", help="idea ID, e.g. EN-002")
    st.add_argument("status")
    add_brand(st)
    st.set_defaults(func=cmd_status)

    du = s.add_parser("dupes", help="find possible duplicate ideas within each language")
    add_brand(du)
    add_language(du)
    du.set_defaults(func=cmd_dupes)

    ck = s.add_parser("check", help="report inconsistencies in the idea lists (changes nothing)")
    add_brand(ck)
    add_language(ck)
    ck.set_defaults(func=cmd_check)

    un = s.add_parser("unlink", help="return an idea to the backlog after its project was deleted")
    un.add_argument("idea", help="idea ID, e.g. EN-002")
    add_brand(un)
    un.set_defaults(func=cmd_unlink)
