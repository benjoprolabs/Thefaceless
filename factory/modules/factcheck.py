"""Fact-Checking System (Phase 2, M5, v0.4.5).

04_factcheck/factcheck.md keeps its Markdown table, one row per [F#] claim:

    | Ref | Claim | Source(s) | Verdict | Fix |
    | F1  | An octopus has three hearts | S1, S3 | ✅ | |

  Ref        F1, F2, ... (the [F#] markers in 03_script/script.md)
  Source(s)  source IDs from 01_research/sources.csv (S1, S3, ...)
  Verdict    ✅ confirmed · ⚠️ needs softer wording · ❌ remove or replace
             (also accepted: ok / soft / remove)
  Fix        what was changed (required for ⚠️)

Columns are read by position, so tables made from the Phase 1 template work.

Commands:
  factcheck sync P     adds a row for each [F#] claim that has none, with the
                       claim's sentence pre-filled; edited rows are never changed
  factcheck check P    the Fact check rules of PHASE2_PLAN.md §7
  factcheck report P   summary of claims, verdicts and sources
"""

import re

from factory.core.checks import FAIL, WARN, Finding, format_finding, register
from factory.core.config import FactoryError
from factory.core.errors import display_path
from factory.core.files import read_text, write_text_exact
from factory.core.projects import find_project
from factory.modules import research, scripts

FILE = "04_factcheck/factcheck.md"
REF = re.compile(r"^F(\d+)$", re.IGNORECASE)
CELL_SPLIT = re.compile(r"(?<!\\)\|")
SOURCE_ID = re.compile(r"^S\d+$", re.IGNORECASE)
OK, SOFT, REMOVE = "ok", "soft", "remove"
VERDICTS = {"✅": OK, "ok": OK, "⚠️": SOFT, "⚠": SOFT, "soft": SOFT, "❌": REMOVE, "remove": REMOVE}
SYMBOL = {OK: "✅", SOFT: "⚠️", REMOVE: "❌", None: "–"}
PLACEHOLDER_VERDICT = re.compile(r"^✅\s*/\s*⚠️?\s*/\s*❌$")  # the template's "✅ / ⚠️ / ❌"
WEAK_STATUSES = ("unverified", "disputed", "outdated")
LOW_RELIABILITY = 2


# ------------------------------------------------------------ reading factcheck.md

def factcheck_path(ctx, project):
    return project.stage_dir(ctx, "factcheck") / "factcheck.md"


def _cells(line):
    """Cells of a Markdown table row (outer pipes removed, '\\|' kept as text)."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT.split(text)]


def parse_verdict(value):
    """'ok' / 'soft' / 'remove'; None when empty (or the template placeholder);
    'invalid' for anything else."""
    text = (value or "").strip()
    if not text or PLACEHOLDER_VERDICT.match(text):
        return None
    return VERDICTS.get(text.lower(), VERDICTS.get(text.replace("️", ""), "invalid"))


def parse_sources(value):
    """Source IDs cited in a cell ('S1, S3' / 'S1 S3' / 'S1;S3'), upper-cased, in order."""
    return [s.upper() for s in re.split(r"[\s,;/]+", (value or "").strip()) if s]


def parse_rows(text):
    """[{'ref': 1, 'claim', 'sources' [ids], 'sources_text', 'verdict', 'verdict_text', 'fix', 'line'}]
    for every table row whose first cell is F# (in file order)."""
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        m = REF.match(cells[0]) if cells else None
        if not m:
            continue
        cells += [""] * (5 - len(cells))
        rows.append({"ref": int(m.group(1)), "claim": cells[1], "sources_text": cells[2],
                     "sources": parse_sources(cells[2]), "verdict_text": cells[3],
                     "verdict": parse_verdict(cells[3]), "fix": cells[4], "line": number})
    return rows


def row_is_blank(row):
    """True for a row nobody has filled in (e.g. the template's 'F1' row)."""
    return not (row["claim"] or row["sources_text"] or row["fix"]) and row["verdict"] is None


# ------------------------------------------------------------ claims in the script

def claim_sentences(ctx, project):
    """{claim number: sentence} for each [F#] in the script, markers removed.
    The first sentence that contains the marker is used."""
    found = {}
    path = scripts.script_path(ctx, project)
    if not path.exists():
        return found
    for scene in scripts.parse_scenes(read_text(path)):
        for sentence in scripts.sentences(scene["narration"]):
            for n in scripts.CLAIM.findall(sentence):
                found.setdefault(int(n), scripts.spoken_text(sentence))
    return dict(sorted(found.items()))


# ------------------------------------------------------------ sync

def _row_line(ref, claim):
    return f"| F{ref:<3}| {claim.replace('|', '/')} | | | |"


def sync(ctx, project):
    """Add a row for each [F#] claim in the script that has none, with its
    sentence pre-filled. A blank row for the claim (like the template's F1 row)
    is filled in; any row with something written in it is never changed.
    Everything else in factcheck.md stays byte-for-byte the same.
    Returns (added [refs], filled [refs])."""
    path = factcheck_path(ctx, project)
    if not path.exists():
        raise FactoryError(f"factcheck.md is missing: {display_path(path, ctx.paths.root)}. "
                           "Restore it with: python -m factory migrate --apply")
    claims = claim_sentences(ctx, project)
    text = read_text(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    rows = parse_rows(text)
    by_ref = {}
    for row in rows:
        by_ref.setdefault(row["ref"], row)
    filled = []
    for ref, sentence in claims.items():
        row = by_ref.get(ref)
        if row and row_is_blank(row) and sentence:
            old = lines[row["line"] - 1]
            ending = old[len(old.rstrip("\r\n")):]
            lines[row["line"] - 1] = _row_line(ref, sentence) + ending
            filled.append(ref)
    missing = [ref for ref in claims if ref not in by_ref]
    if missing:
        if rows:
            at = max(r["line"] for r in rows)  # after the last claim row
        else:
            at = next((i + 1 for i, line in enumerate(lines)
                       if re.match(r"^\s*\|[\s:|-]*-[\s:|-]*\|?\s*$", line)), None)  # after |---|
            if at is None:
                raise FactoryError("factcheck.md has no claims table. Add the header rows first:\n"
                                   "  | Ref | Claim | Source(s) | Verdict | Fix |\n  |-----|-------|-----------|---------|-----|")
        if at > 0 and not lines[at - 1].endswith(("\n", "\r")):
            lines[at - 1] += newline
        lines[at:at] = [_row_line(ref, claims[ref]) + newline for ref in missing]
    if missing or filled:
        write_text_exact(path, "".join(lines))
    return missing, filled


# ------------------------------------------------------------ checks (plan §7)

def _source_label(row):
    status = (row.get("verification_status") or "").strip().lower() or "unverified"
    reliability = (row.get("reliability") or "").strip()
    return status, reliability


def _past_factcheck(ctx, project):
    ids = [s["id"] for s in ctx.config.stages]
    return project.stage in ids and ids.index(project.stage) > ids.index("factcheck")


@register("factcheck")
def check_factcheck(ctx, project):
    """Fact check rules (plan §7). Claims missing a row are reported by
    scripts.check_claims_covered (FACTCHECK_MISSING_CLAIM).

    A project that has already moved past Fact Check (e.g. a Phase 1 project
    whose rows cite research.md numbers, not sources.csv IDs) gets WARN instead
    of FAIL, as approved for Research in M2; the gate itself only ever checks
    the project's current stage."""
    findings = _factcheck_findings(ctx, project)
    if _past_factcheck(ctx, project):
        findings = [f._replace(level=WARN, message=f.message + " (project is already past Fact Check)")
                    if f.level == FAIL else f for f in findings]
    return findings


def _factcheck_findings(ctx, project):
    path = factcheck_path(ctx, project)
    if not path.exists():
        return [Finding(FAIL, "FACTCHECK_MISSING", "factcheck.md is missing "
                        "(restore it with: python -m factory migrate --apply)", FILE)]
    rows = parse_rows(read_text(path))
    script_claims = set(claim_sentences(ctx, project))
    try:
        _, source_rows = research.load_sources(ctx, project)
    except FactoryError as e:
        return [Finding(FAIL, "FACTCHECK_SOURCES_FILE", str(e), research.FILE)]
    sources = {(r.get("id") or "").strip().upper(): r for r in source_rows if (r.get("id") or "").strip()}

    findings, seen = [], set()
    for row in rows:
        ref, label = row["ref"], f"F{row['ref']}"
        if ref in seen:
            findings.append(Finding(WARN, "FACTCHECK_DUPLICATE_ROW",
                                    f"{label} has more than one row; only the first is used (line {row['line']})", FILE))
            continue
        seen.add(ref)
        in_script = ref in script_claims
        verdict = row["verdict"]
        if verdict == "invalid":
            findings.append(Finding(FAIL, "FACTCHECK_VERDICT", f"{label}: unknown verdict '{row['verdict_text']}' "
                                    "(use ✅ / ⚠️ / ❌, or ok / soft / remove)", FILE))
            continue
        if verdict == REMOVE:
            if in_script:
                findings.append(Finding(FAIL, "FACTCHECK_REMOVED_IN_SCRIPT",
                                        f"{label} is marked ❌ but is still in the script; remove or replace it", FILE))
            continue
        if verdict == SOFT and not row["fix"]:
            findings.append(Finding(FAIL, "FACTCHECK_NO_FIX", f"{label} is marked ⚠️ but the Fix column is empty; "
                                    "say how the wording was softened", FILE))
        if not in_script:
            continue  # a row for a claim no longer in the script needs nothing more
        if verdict is None:
            findings.append(Finding(FAIL, "FACTCHECK_NO_VERDICT", f"{label} has no verdict (✅ / ⚠️ / ❌)", FILE))
        if not row["sources"]:
            findings.append(Finding(FAIL, "FACTCHECK_NO_SOURCE", f"{label} cites no source "
                                    f"(add source IDs such as S1 from {research.FILE})", FILE))
            continue
        unknown = [s for s in row["sources"] if s not in sources]
        if unknown:
            hint = " (cite sources by ID, e.g. S1)" if any(not SOURCE_ID.match(s) for s in unknown) else ""
            findings.append(Finding(FAIL, "FACTCHECK_UNKNOWN_SOURCE", f"{label} cites " + ", ".join(unknown)
                                    + f", not found in {research.FILE}{hint}", FILE))
        known = [sources[s] for s in row["sources"] if s in sources]
        if not known:
            continue
        labels = [_source_label(s) for s in known]
        if all(status in WEAK_STATUSES for status, _ in labels):
            listed = ", ".join(f"{s['id'].strip().upper()} {status}" for s, (status, _) in zip(known, labels))
            findings.append(Finding(FAIL, "FACTCHECK_WEAK_SOURCES", f"{label} is supported only by unverified, "
                                    f"disputed or outdated sources ({listed}); verify one with: "
                                    f"python -m factory research verify {project.id} S# verified", FILE))
        elif all(rel.isdigit() and int(rel) <= LOW_RELIABILITY for _, rel in labels):
            findings.append(Finding(WARN, "FACTCHECK_LOW_RELIABILITY", f"{label} is supported only by sources "
                                    f"with reliability {LOW_RELIABILITY} or lower", FILE))
    return findings


# ------------------------------------------------------------ report

def report(ctx, project):
    """Summary data: claims, rows, verdict counts and per-claim details."""
    path = factcheck_path(ctx, project)
    rows = parse_rows(read_text(path)) if path.exists() else []
    claims = claim_sentences(ctx, project)
    try:
        _, source_rows = research.load_sources(ctx, project)
    except FactoryError:
        source_rows = []
    sources = {(r.get("id") or "").strip().upper(): r for r in source_rows}
    first = {}
    for row in rows:
        first.setdefault(row["ref"], row)
    refs = sorted(set(claims) | set(first))
    details = []
    for ref in refs:
        row = first.get(ref)
        cited = []
        for sid in (row["sources"] if row else []):
            src = sources.get(sid)
            cited.append(f"{sid} ({_source_label(src)[0]})" if src else f"{sid} (not found)")
        details.append({"ref": ref, "in_script": ref in claims, "has_row": row is not None,
                        "verdict": row["verdict"] if row else None, "sources": cited,
                        "claim": (row["claim"] if row and row["claim"] else claims.get(ref, ""))})
    counts = {k: sum(1 for d in details if d["verdict"] == k) for k in (OK, SOFT, REMOVE, None, "invalid")}
    return {"claims": len(claims), "rows": len(first), "details": details, "counts": counts}


# ------------------------------------------------------------ commands

def cmd_sync(args, ctx):
    p = find_project(ctx, args.project)
    added, filled = sync(ctx, p)
    if not added and not filled:
        print("factcheck.md already has a row for every [F#] claim in the script. Nothing changed.")
        return 0
    if filled:
        print("Filled blank row(s): " + ", ".join(f"F{r}" for r in filled))
    if added:
        print("Added row(s): " + ", ".join(f"F{r}" for r in added))
    print("Next: add source IDs (S1, ...) and a verdict for each, then run: "
          f"python -m factory factcheck check {p.id}")
    return 0


def cmd_check(args, ctx):
    p = find_project(ctx, args.project)
    findings = scripts.check_claims_covered(ctx, p) + check_factcheck(ctx, p)
    for f in findings:
        print(f"  {format_finding(f)}")
    fails = sum(f.level == FAIL for f in findings)
    print("Fact check OK." if not findings else f"{fails} FAIL, {len(findings) - fails} WARN.")
    return 1 if fails else 0


def cmd_report(args, ctx):
    p = find_project(ctx, args.project)
    r = report(ctx, p)
    c = r["counts"]
    print(f"Fact check report: {p.id}")
    print(f"Claims in the script: {r['claims']}   Rows: {r['rows']}   "
          f"✅ {c[OK]}  ⚠️ {c[SOFT]}  ❌ {c[REMOVE]}  no verdict {c[None] + c['invalid']}")
    if r["details"]:
        print(f"{'REF':<5} {'VERDICT':<8} {'IN SCRIPT':<10} {'SOURCES':<28} CLAIM")
        for d in r["details"]:
            verdict = SYMBOL.get(d["verdict"], "?") if d["has_row"] else "no row"
            claim = d["claim"] if len(d["claim"]) <= 60 else d["claim"][:57] + "..."
            print(f"F{d['ref']:<4} {verdict:<8} {'yes' if d['in_script'] else 'no':<10} "
                  f"{', '.join(d['sources']) or '-':<28} {claim}")
    findings = scripts.check_claims_covered(ctx, p) + check_factcheck(ctx, p)
    fails = sum(f.level == FAIL for f in findings)
    print(f"Checks: {fails} FAIL, {len(findings) - fails} WARN"
          + (f" (details: python -m factory factcheck check {p.id})" if findings else ""))
    return 0


def register(sub):
    p = sub.add_parser("factcheck", help="Fact-Checking System: sync claims, check verdicts and sources, report")
    s = p.add_subparsers(metavar="action", required=True)
    sy = s.add_parser("sync", help="add a row for each new [F#] claim (never changes edited rows)")
    sy.add_argument("project")
    sy.set_defaults(func=cmd_sync)
    ck = s.add_parser("check", help="check claims, verdicts and sources (changes nothing)")
    ck.add_argument("project")
    ck.set_defaults(func=cmd_check)
    rp = s.add_parser("report", help="summary of claims, verdicts and sources")
    rp.add_argument("project")
    rp.set_defaults(func=cmd_report)
