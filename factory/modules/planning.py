"""Content Planning (Phase 2, M3, v0.4.3).

Reads the existing 02_planning/plan.md (its headings are unchanged):
  ## Angle / hook             the hook text
  ## Outline                  numbered points "1. ...", "2. ..."
  ## SEO                      "- **Primary keyword:** ..." / "- **Secondary keywords:** ..."
  ## Target publish date      YYYY-MM-DD

project.json gains an optional "planned_publish" (YYYY-MM-DD), set with
`plan set-date`; the publishing calendar uses it (or the plan's date).
"""

import re
from collections import defaultdict
from datetime import date

from factory.core.checks import FAIL, WARN, Finding, register
from factory.core.config import FactoryError
from factory.core.errors import display_path
from factory.core.files import read_text, today, write_text_exact
from factory.core.options import add_brand, add_division, add_language, brand_id
from factory.core.projects import find_project, iter_projects

FILE = "02_planning/plan.md"
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_SECONDS_PER_POINT = {"short": 12, "long": 90}
DEFAULT_MAX_PER_CHANNEL_PER_DAY = 2


# ------------------------------------------------------------ reading plan.md

def plan_path(ctx, project):
    return project.stage_dir(ctx, "planning") / "plan.md"


def sections(text):
    """{lower-case heading: body} for every '## ' heading (comments removed)."""
    result, current = {}, None
    for line in COMMENT.sub("", text).splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            current = m.group(1).strip().lower()
            result[current] = []
        elif current is not None:
            result[current].append(line)
    return {k: "\n".join(v).strip() for k, v in result.items()}


def _section(secs, *words):
    for heading, body in secs.items():
        if all(w in heading for w in words):
            return body
    return None


def parse_plan(text):
    """Return {'hook', 'outline' [points], 'primary_keyword', 'secondary_keywords',
    'date' (raw text), 'missing_sections' [names]}."""
    secs = sections(text)
    hook = _section(secs, "hook")
    outline = _section(secs, "outline")
    seo = _section(secs, "seo")
    target = _section(secs, "publish date")
    missing = [name for name, body in (("Angle / hook", hook), ("Outline", outline), ("SEO", seo),
                                       ("Target publish date", target)) if body is None]
    points = []
    for line in (outline or "").splitlines():
        m = re.match(r"^\s*\d+[.)]\s*(.*)$", line)
        if m and m.group(1).strip():
            points.append(m.group(1).strip())

    def keyword(label):
        # [ \t]* (not \s*): an empty value must not run on into the next line
        m = re.search(rf"^[ \t]*[-*][ \t]*\**{label}:?\**:?[ \t]*(.*)$", seo or "", re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    first_line = next((l.strip() for l in (target or "").splitlines() if l.strip()), "")
    return {"hook": (hook or "").strip(), "outline": points, "primary_keyword": keyword("primary keyword"),
            "secondary_keywords": keyword("secondary keywords"), "date": first_line, "missing_sections": missing}


def valid_date(value):
    if not ISO_DATE.match(value or ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def planned_date(ctx, project):
    """The project's planned publish date: project.json first, then plan.md."""
    value = (project.meta.get("planned_publish") or "").strip()
    if not value and plan_path(ctx, project).exists():
        value = parse_plan(read_text(plan_path(ctx, project)))["date"]
    return value if valid_date(value) else None


def rules(ctx):
    planning = ctx.config.rules.get("planning", {})
    per_point = {**DEFAULT_SECONDS_PER_POINT, **planning.get("seconds_per_outline_point", {})}
    limit = planning.get("max_videos_per_channel_per_day", DEFAULT_MAX_PER_CHANNEL_PER_DAY)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise FactoryError("config/rules.json: planning.max_videos_per_channel_per_day must be a whole number ≥ 1")
    return per_point, limit


# ------------------------------------------------------------ calendar

def calendar(ctx, brand, language=None, division=None, start=None, end=None):
    """[(date, project)] sorted, plus {(language, date): [projects]} clashes."""
    entries = []
    for p in iter_projects(ctx, brand=brand):
        when = planned_date(ctx, p)
        if when:
            entries.append((when, p))
    _, limit = rules(ctx)
    per_channel_day = defaultdict(list)
    for when, p in entries:  # clashes are counted over the whole brand, before filtering
        per_channel_day[(p.language, when)].append(p)
    clashes = {k: v for k, v in per_channel_day.items() if len(v) > limit}
    shown = [(w, p) for w, p in entries
             if (not language or p.language == language) and (not division or p.meta["division"] == division)
             and (not start or w >= start) and (not end or w <= end)]
    return sorted(shown, key=lambda e: (e[0], e[1].id)), clashes


# ------------------------------------------------------------ checks

@register("planning")
def check_plan(ctx, project):
    """Plan §7: FAIL for a missing hook, < 3 outline points, no primary keyword
    or an invalid/missing date; WARN for an outline that doesn't fit the format,
    a date out of sync with project.json, or a channel-day clash."""
    path = plan_path(ctx, project)
    if not path.exists():
        return [Finding(FAIL, "PLAN_MISSING", "plan.md is missing", FILE)]
    plan = parse_plan(read_text(path))
    findings = []
    for name in plan["missing_sections"]:
        findings.append(Finding(FAIL, "PLAN_SECTION", f"section '## {name}' is missing", FILE))
    if "Angle / hook" not in plan["missing_sections"] and not plan["hook"]:
        findings.append(Finding(FAIL, "PLAN_HOOK", "the hook is empty (## Angle / hook)", FILE))
    if "Outline" not in plan["missing_sections"] and len(plan["outline"]) < 3:
        findings.append(Finding(FAIL, "PLAN_OUTLINE",
                                f"the outline has {len(plan['outline'])} point(s); at least 3 are needed", FILE))
    if "SEO" not in plan["missing_sections"] and not plan["primary_keyword"]:
        findings.append(Finding(FAIL, "PLAN_KEYWORD", "no primary keyword (## SEO)", FILE))
    if "Target publish date" not in plan["missing_sections"]:
        if not plan["date"]:
            findings.append(Finding(FAIL, "PLAN_DATE", "no target publish date (YYYY-MM-DD; or use: plan set-date)", FILE))
        elif not valid_date(plan["date"]):
            findings.append(Finding(FAIL, "PLAN_DATE", f"invalid target publish date '{plan['date']}' (use YYYY-MM-DD)", FILE))
    stored = (project.meta.get("planned_publish") or "").strip()
    if stored and not valid_date(stored):
        findings.append(Finding(FAIL, "PLAN_DATE", f"project.json planned_publish '{stored}' is not a valid date",
                                "project.json"))
    elif stored and valid_date(plan["date"]) and stored != plan["date"]:
        findings.append(Finding(WARN, "PLAN_DATE_SYNC", f"plan.md says {plan['date']} but planned_publish is "
                                f"{stored}; run: python -m factory plan set-date {project.id} YYYY-MM-DD", FILE))
    per_point, limit = rules(ctx)
    fmt = project.meta["format"]
    if len(plan["outline"]) >= 3 and fmt in per_point:
        spec = ctx.config.formats[fmt]
        estimate = len(plan["outline"]) * per_point[fmt]
        if not spec["min_seconds"] <= estimate <= spec["max_seconds"]:
            findings.append(Finding(WARN, "PLAN_OUTLINE_LENGTH",
                                    f"{len(plan['outline'])} outline points ≈ {estimate} s, outside "
                                    f"{spec['min_seconds']}–{spec['max_seconds']} s for {fmt}-form "
                                    f"({per_point[fmt]} s per point)", FILE))
    when = planned_date(ctx, project)
    if when:
        brand = project.meta.get("brand") or ctx.config.settings["default_brand"]
        _, clashes = calendar(ctx, brand)
        same_day = clashes.get((project.language, when), [])
        if same_day:
            others = ", ".join(p.id for p in same_day if p.id != project.id)
            findings.append(Finding(WARN, "PLAN_CLASH", f"{len(same_day)} videos planned for the "
                                    f"{ctx.config.languages[project.language]['name']} channel on {when} "
                                    f"(limit {limit}): {others}", FILE))
    return findings


# ------------------------------------------------------------ set-date

def set_date(ctx, project, value):
    """Store planned_publish in project.json and write the same date into the
    plan's '## Target publish date' section (only that section changes)."""
    value = (value or "").strip()
    if value.lower() == "today":
        value = today()
    if not valid_date(value):
        raise FactoryError(f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-12-01")
    path = plan_path(ctx, project)
    updated_plan = False
    if path.exists():
        text = read_text(path)
        heading = re.search(r"^##\s+Target publish date[ \t]*\r?\n", text, re.MULTILINE | re.IGNORECASE)
        if heading:
            # Change only the date line (the first non-empty line of the section);
            # everything else in plan.md stays byte-for-byte the same.
            start = heading.end()
            following = re.search(r"^##\s", text[start:], re.MULTILINE)
            end = start + following.start() if following else len(text)
            body = text[start:end]
            line = re.search(r"^[ \t]*(?!<!--)\S[^\r\n]*", body, re.MULTILINE)
            if line:
                body = body[:line.start()] + value + body[line.end():]
            else:
                body = value + "\n" + body
            write_text_exact(path, text[:start] + body + text[end:])
            updated_plan = True
    old = project.meta.get("planned_publish", "")
    project.meta["planned_publish"] = value
    project.save()
    return old, value, updated_plan


# ------------------------------------------------------------ commands

def cmd_check(args, ctx):
    from factory.core.checks import format_finding
    p = find_project(ctx, args.project)
    findings = check_plan(ctx, p)
    for f in findings:
        print(f"  {format_finding(f)}")
    fails = sum(f.level == FAIL for f in findings)
    print("Plan OK." if not findings else f"{fails} FAIL, {len(findings) - fails} WARN.")
    return 1 if fails else 0


def cmd_set_date(args, ctx):
    p = find_project(ctx, args.project)
    old, new, updated_plan = set_date(ctx, p, args.date)
    print(f"{p.id}: planned publish date {old or '-'} → {new}")
    if not updated_plan:
        print(f"  (plan.md has no '## Target publish date' section; only project.json was updated: "
              f"{display_path(plan_path(ctx, p), ctx.paths.root)})")
    return 0


def _optional_date(value, name):
    if not value:
        return None
    if not valid_date(value):
        raise FactoryError(f"--{name}: invalid date '{value}' (use YYYY-MM-DD)")
    return value


def cmd_calendar(args, ctx):
    brand = brand_id(args, ctx)
    start, end = _optional_date(args.start, "from"), _optional_date(args.end, "to")
    entries, clashes = calendar(ctx, brand, args.lang, args.division, start, end)
    if not entries:
        print("No planned publish dates in this range. Set one with: python -m factory plan set-date P YYYY-MM-DD")
        return 0
    print(f"{'DATE':<11} {'LANG':<4} {'DIVISION':<18} {'STAGE':<17} PROJECT")
    for when, p in entries:
        flag = "  ⚠ clash" if (p.language, when) in clashes else ""
        print(f"{when:<11} {p.language:<4} {p.meta['division']:<18} {ctx.config.stage(p.stage)['label']:<17} "
              f"{p.id}{flag}")
    _, limit = rules(ctx)
    for (language, when), projects in sorted(clashes.items(), key=lambda kv: kv[0][1]):
        if any(e[0] == when and e[1].language == language for e in entries):
            ctx.warnings[f"clash:{language}:{when}"] = (
                f"{len(projects)} videos planned for the {ctx.config.languages[language]['name']} channel on "
                f"{when} (limit {limit} per day; config/rules.json)")
    return 0


def register(sub):
    p = sub.add_parser("plan", help="Content Planning: check plans, set dates, calendar")
    s = p.add_subparsers(metavar="action", required=True)
    ck = s.add_parser("check", help="check a project's plan.md (changes nothing)")
    ck.add_argument("project")
    ck.set_defaults(func=cmd_check)
    sd = s.add_parser("set-date", help="set the planned publish date (project.json and plan.md)")
    sd.add_argument("project")
    sd.add_argument("date", help="YYYY-MM-DD or 'today'")
    sd.set_defaults(func=cmd_set_date)
    ca = s.add_parser("calendar", help="planned publish dates across projects")
    add_brand(ca)
    add_language(ca)
    add_division(ca)
    ca.add_argument("--from", dest="start", help="YYYY-MM-DD")
    ca.add_argument("--to", dest="end", help="YYYY-MM-DD")
    ca.set_defaults(func=cmd_calendar)
