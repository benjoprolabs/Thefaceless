"""Research Engine (Phase 2, M2, v0.4.2): structured source tracking.

Each project keeps:
  01_research/research.md   detailed research notes (narrative, findings, competition)
  01_research/sources.csv   one row per source, used by fact-checking (M5)

sources.csv columns:
  id                   S1, S2, ... (assigned automatically, unique)
  title                required
  url                  full http(s) link; empty for offline sources (books, interviews)
  publisher            optional
  type                 primary | official | study | secondary | news | book | other
  published            optional, YYYY-MM-DD, not in the future
  accessed             required, YYYY-MM-DD, not in the future
  verification_status  unverified (default) | verified | disputed | outdated
  reliability          optional, 1-5
  notes                optional

Links are only checked as text; they are never opened (the factory works offline).
"""

import re
from datetime import date, timedelta

from factory.core.checks import FAIL, WARN, Finding, register
from factory.core.config import FactoryError
from factory.core.errors import display_path
from factory.core.files import read_csv_table, today, write_csv
from factory.core.projects import find_project
from factory.core.validation import check_date, check_web_url, normalise_url

FIELDS = ["id", "title", "url", "publisher", "type", "published", "accessed",
          "verification_status", "reliability", "notes"]
REQUIRED_COLUMNS = ["id", "title", "url", "type", "accessed", "verification_status"]
TYPES = ("primary", "official", "study", "secondary", "news", "book", "other")
STATUSES = ("unverified", "verified", "disputed", "outdated")
SOURCE_ID = re.compile(r"^S(\d+)$", re.IGNORECASE)
FILE = "01_research/sources.csv"


# ------------------------------------------------------------ file access

def sources_path(ctx, project):
    return project.stage_dir(ctx, "research") / "sources.csv"


def load_sources(ctx, project):
    """Return (exists, rows). Excel-saved files are accepted; a file missing
    required columns raises a clear FactoryError."""
    path = sources_path(ctx, project)
    if not path.exists():
        return False, []
    header, rows = read_csv_table(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if header and missing:
        raise FactoryError(f"{display_path(path, ctx.paths.root)} is missing column(s): {', '.join(missing)}. "
                           f"The first row must be: {','.join(FIELDS)}")
    return True, [r for r in rows if any((v or "").strip() for v in r.values())]


def save_sources(ctx, project, rows):
    """Write sources.csv; extra columns added by users (e.g. in Excel) are kept."""
    write_csv(sources_path(ctx, project), rows, FIELDS)


def next_source_id(rows):
    numbers = [int(m.group(1)) for m in (SOURCE_ID.match((r.get("id") or "").strip()) for r in rows) if m]
    return f"S{max(numbers, default=0) + 1}"


def find_source(rows, source_id):
    for row in rows:
        if (row.get("id") or "").strip().lower() == source_id.strip().lower():
            return row
    raise FactoryError(f"Source '{source_id}' not found. See: python -m factory research sources <project>")


# ------------------------------------------------------------ validation

def parse_date(value, field, required):
    value = (value or "").strip()
    if not value:
        if required:
            raise FactoryError(f"--{field} is required (YYYY-MM-DD or 'today')")
        return ""
    if value.lower() == "today":
        return today()
    try:
        return check_date(value)
    except FactoryError as e:
        raise FactoryError(f"{field}: {e}") from None


def parse_choice(value, field, choices, default=None):
    value = (value or "").strip().lower()
    if not value and default:
        return default
    if value not in choices:
        raise FactoryError(f"{field} must be one of: {', '.join(choices)} (got '{value}')")
    return value


def parse_reliability(value):
    if value is None or str(value).strip() == "":
        return ""
    text = str(value).strip()
    if not re.fullmatch(r"[1-5]", text):
        raise FactoryError(f"reliability must be a whole number from 1 to 5 (got '{text}')")
    return text


def parse_url(value):
    value = (value or "").strip()
    return check_web_url(value)[0] if value else ""


def row_findings(ctx, project, rows):
    """Per-source findings (FAIL for invalid values, WARN for duplicates and old sources)."""
    findings = []
    seen_ids, seen_urls = {}, {}
    max_age = ctx.config.divisions.get(project.meta["division"], {}).get("source_max_age_days")

    def add(level, code, label, message):
        findings.append(Finding(level, code, f"{label}: {message}", FILE))

    for n, row in enumerate(rows, 1):
        sid = (row.get("id") or "").strip()
        label = sid or f"row {n}"
        if not SOURCE_ID.match(sid):
            add(FAIL, "SOURCE_ID", label, "id must look like S1, S2, ...")
        elif sid.lower() in seen_ids:
            add(FAIL, "SOURCE_DUPLICATE_ID", label, f"id is used more than once (also row {seen_ids[sid.lower()]})")
        else:
            seen_ids[sid.lower()] = n
        if not (row.get("title") or "").strip():
            add(FAIL, "SOURCE_TITLE", label, "title is required")
        for field, check in (("url", parse_url),
                             ("type", lambda v: parse_choice(v, "type", TYPES)),
                             ("verification_status", lambda v: parse_choice(v, "verification_status", STATUSES)),
                             ("reliability", parse_reliability),
                             ("published", lambda v: parse_date(v, "published", required=False))):
            try:
                check(row.get(field))
            except FactoryError as e:
                add(FAIL, f"SOURCE_{field.upper()}", label, str(e))
        accessed = None
        try:
            accessed = parse_date(row.get("accessed"), "accessed", required=True)
        except FactoryError as e:
            add(FAIL, "SOURCE_ACCESSED", label, str(e).replace("--accessed", "accessed"))
        url = (row.get("url") or "").strip()
        if url:
            key = normalise_url(url)
            if key in seen_urls:
                add(WARN, "SOURCE_DUPLICATE_URL", label, f"same link as {seen_urls[key]}")
            else:
                seen_urls[key] = label
        if accessed and max_age:
            age = (date.today() - date.fromisoformat(accessed)).days
            if age > max_age:
                add(WARN, "SOURCE_OLD", label, f"accessed {age} days ago; {ctx.config.divisions[project.meta['division']]['name']} "
                    f"sources should be re-checked within {max_age} days")
    return findings


@register("research")
def check_sources(ctx, project):
    """Research-stage checks (plan §7). Without sources, a project still at
    Research gets a FAIL (it can't leave Research); a project that already
    moved past Research gets a WARN (approved M2 decision 1)."""
    at_research = project.stage == "research"
    level = FAIL if at_research else WARN
    try:
        exists, rows = load_sources(ctx, project)
    except FactoryError as e:
        return [Finding(FAIL, "SOURCES_FILE", str(e), FILE)]
    if not exists:
        return [Finding(level, "SOURCES_MISSING",
                        "no sources.csv yet. Add sources with: python -m factory research add-source "
                        f"{project.id} ... (or create the file with: python -m factory migrate --apply)", FILE)]
    if not rows:
        return [Finding(level, "SOURCES_EMPTY",
                        f"no sources recorded. Add at least one: python -m factory research add-source {project.id} ...",
                        FILE)]
    return row_findings(ctx, project, rows)


# ------------------------------------------------------------ operations

def add_source(ctx, project, title, url, source_type, accessed, published="", publisher="",
               reliability=None, notes=""):
    """Validate and append one source. Returns (row, duplicate_of or None)."""
    if not (title or "").strip():
        raise FactoryError("--title is required")
    row = {
        "title": title.strip(),
        "url": parse_url(url),
        "publisher": (publisher or "").strip(),
        "type": parse_choice(source_type, "type", TYPES),
        "published": parse_date(published, "published", required=False),
        "accessed": parse_date(accessed, "accessed", required=True),
        "verification_status": "unverified",
        "reliability": parse_reliability(reliability),
        "notes": re.sub(r"\s*[\r\n]+\s*", " ", notes or "").strip(),
    }
    _, rows = load_sources(ctx, project)
    duplicate = None
    if row["url"]:
        key = normalise_url(row["url"])
        duplicate = next((r for r in rows if (r.get("url") or "").strip() and normalise_url(r["url"]) == key), None)
    row = {"id": next_source_id(rows), **row}
    save_sources(ctx, project, rows + [row])  # creates sources.csv if it was missing
    return row, duplicate


def set_verification(ctx, project, source_id, status):
    status = parse_choice(status, "status", STATUSES)
    exists, rows = load_sources(ctx, project)
    if not exists:
        raise FactoryError(f"{project.id} has no sources.csv yet. Add sources with: research add-source")
    row = find_source(rows, source_id)
    old = (row.get("verification_status") or "").strip()
    if old == status:
        raise FactoryError(f"{row['id']} is already '{status}'")
    row["verification_status"] = status
    save_sources(ctx, project, rows)
    return row["id"], old, status


def _dedupe_key(row):
    url = (row.get("url") or "").strip()
    if url:
        return ("url", normalise_url(url))
    return ("title", (row.get("title") or "").strip().casefold(), (row.get("publisher") or "").strip().casefold())


def copy_sources(ctx, target, origin):
    """Copy sources from `origin` into `target` (approved M2 decision 3).

    Every value is copied exactly, including verification_status, accessed
    and published: copying never makes a source look freshly verified. Only
    the id changes (the next free S number in the target). Sources already in
    the target (same link, or same title + publisher when there is no link)
    are skipped. The origin project's file is only read, never written."""
    if origin.folder == target.folder:
        raise FactoryError("Choose a different project to copy sources from")
    exists, incoming = load_sources(ctx, origin)
    if not exists or not incoming:
        raise FactoryError(f"{origin.id} has no sources to copy")
    _, rows = load_sources(ctx, target)
    keys = {_dedupe_key(r) for r in rows}
    copied, skipped = [], []
    for source in incoming:
        key = _dedupe_key(source)
        if key in keys:
            skipped.append(source)
            continue
        new = dict(source)  # all columns, values unchanged
        new["id"] = next_source_id(rows)
        rows.append(new)
        keys.add(key)
        copied.append((source.get("id", ""), new["id"], new))
    if copied:
        save_sources(ctx, target, rows)
    return copied, skipped


# ------------------------------------------------------------ commands

def cmd_sources(args, ctx):
    p = find_project(ctx, args.project)
    exists, rows = load_sources(ctx, p)
    if not rows:
        print(f"{p.id}: no sources yet. Add one with: python -m factory research add-source {p.id} "
              "--title \"...\" --url https://... --type study --accessed today")
        return 0
    print(f"{p.id}: {len(rows)} source(s)")
    print(f"  {'ID':<5} {'STATUS':<11} {'TYPE':<9} {'ACCESSED':<10} {'REL':<3} TITLE")
    for r in rows:
        print(f"  {r.get('id', ''):<5} {r.get('verification_status', ''):<11} {r.get('type', ''):<9} "
              f"{r.get('accessed', ''):<10} {r.get('reliability', '') or '-':<3} {r.get('title', '')}")
        if (r.get("url") or "").strip():
            print(f"        {r['url']}")
    return 0


def cmd_add_source(args, ctx):
    p = find_project(ctx, args.project)
    row, duplicate = add_source(ctx, p, args.title, args.url, args.type, args.accessed, args.published,
                                args.publisher, args.reliability, args.notes)
    print(f"Added {row['id']} ({row['verification_status']}): {row['title']}")
    if duplicate is not None:
        ctx.warnings[f"source-dup:{p.id}:{row['id']}"] = (
            f"{row['id']} has the same link as {duplicate.get('id')} ({duplicate.get('title')})")
    return 0


def cmd_verify(args, ctx):
    p = find_project(ctx, args.project)
    sid, old, new = set_verification(ctx, p, args.source, args.status)
    print(f"{p.id} {sid}: {old or '-'} → {new}")
    return 0


def cmd_check(args, ctx):
    from factory.core.checks import format_finding
    p = find_project(ctx, args.project)
    findings = check_sources(ctx, p)
    for f in findings:
        print(f"  {format_finding(f)}")
    fails = [f for f in findings if f.level == FAIL]
    print("Sources OK." if not findings else f"{len(fails)} FAIL, {len(findings) - len(fails)} WARN.")
    return 1 if fails else 0


def cmd_copy(args, ctx):
    target = find_project(ctx, args.project)
    origin = find_project(ctx, getattr(args, "from"))
    copied, skipped = copy_sources(ctx, target, origin)
    for old_id, new_id, row in copied:
        print(f"  copied {origin.id} {old_id} → {new_id} ({row.get('verification_status') or '-'}): {row.get('title')}")
    for row in skipped:
        print(f"  skipped {row.get('id')} (already in {target.id}): {row.get('title')}")
    print(f"{len(copied)} copied, {len(skipped)} skipped. Verification status and dates were kept as they were.")
    return 0


def register(sub):
    p = sub.add_parser("research", help="Research Engine: structured sources for a project")
    s = p.add_subparsers(metavar="action", required=True)

    ls = s.add_parser("sources", help="list a project's sources")
    ls.add_argument("project")
    ls.set_defaults(func=cmd_sources)

    ad = s.add_parser("add-source", help="add a source to sources.csv")
    ad.add_argument("project")
    ad.add_argument("--title", required=True)
    ad.add_argument("--url", default="", help="full http(s) link; leave out for books or interviews")
    ad.add_argument("--type", required=True, help=" | ".join(TYPES))
    ad.add_argument("--accessed", required=True, help="YYYY-MM-DD or 'today'")
    ad.add_argument("--published", default="", help="YYYY-MM-DD")
    ad.add_argument("--publisher", default="")
    ad.add_argument("--reliability", help="1-5")
    ad.add_argument("--notes", default="")
    ad.set_defaults(func=cmd_add_source)

    vf = s.add_parser("verify", help="set a source's verification status")
    vf.add_argument("project")
    vf.add_argument("source", help="source ID, e.g. S1")
    vf.add_argument("status", help=" | ".join(STATUSES))
    vf.set_defaults(func=cmd_verify)

    ck = s.add_parser("check", help="check a project's sources (changes nothing)")
    ck.add_argument("project")
    ck.set_defaults(func=cmd_check)

    cp = s.add_parser("copy-sources", help="copy sources from another project (no duplicates)")
    cp.add_argument("project", help="project to copy into")
    cp.add_argument("--from", required=True, help="project to copy from (only read)")
    cp.set_defaults(func=cmd_copy)
