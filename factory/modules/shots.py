"""Shot List Generator (Phase 2, M6, v0.4.6).

06_visuals/shotlist.csv has one row per shot (normally one per script scene):

    scene,start_sec,end_sec,narration_summary,visual_type,visual_description,
    source,license,file,status,asset_id

  status    todo | in_progress | done | removed ("removed" = the scene is no
            longer in the script; set by `shots generate`, delete the row yourself)
  asset_id  optional link to assets/register.csv (AS0001, ...)

Commands:
  shots generate P [--force]  merge with the script: rows you filled in are
                              kept, new scenes are added, times are refreshed,
                              rows of removed scenes get status "removed".
                              --force rebuilds the file from scratch.
                              (`script shotlist` is the same command.)
  shots link P SCENE --asset ID   link a scene's row to a registered asset
  shots check P               the Shot list rules of PHASE2_PLAN.md §7
"""

import re

from factory.core.checks import FAIL, WARN, Finding, format_finding, register
from factory.core.config import FactoryError
from factory.core.errors import display_path
from factory.core.files import read_csv_table, write_csv
from factory.core.projects import find_project
from factory.core.templates import csv_columns
from factory.modules import assets, scripts

FILE = "06_visuals/shotlist.csv"
TIMING = ("start_sec", "end_sec")
DONE, REMOVED, TODO = "done", "removed", "todo"
DEFAULT_MAX_SHOT_SECONDS = {"short": 5}
DEFAULT_SELF_MADE = ["self-made", "own", "original"]


def shotlist_path(ctx, project):
    return project.stage_dir(ctx, "visuals") / "shotlist.csv"


def scene_number(row):
    """The row's scene as an int, or None when it isn't a whole number."""
    text = (row.get("scene") or "").strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


def status(row):
    return (row.get("status") or "").strip().lower()


def _number(value):
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def rules(ctx):
    """M6 settings from config/rules.json "shots" (defaults if missing)."""
    cfg = ctx.config.rules.get("shots", {})
    if not isinstance(cfg, dict):
        raise FactoryError("config/rules.json: shots must be an object { ... }")
    limits = cfg.get("max_shot_seconds", {})
    if not isinstance(limits, dict):
        raise FactoryError("config/rules.json: shots.max_shot_seconds must be like {\"short\": 5}")
    limits = {**DEFAULT_MAX_SHOT_SECONDS, **limits}
    for fmt, value in limits.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise FactoryError(f"config/rules.json: shots.max_shot_seconds.{fmt} must be a number above 0")
    self_made = cfg.get("self_made_sources", DEFAULT_SELF_MADE)
    if not isinstance(self_made, list):
        raise FactoryError("config/rules.json: shots.self_made_sources must be a list of words")
    return limits, {str(s).strip().lower() for s in self_made}


# ------------------------------------------------------------ generate (merge)

def generate(ctx, project, rebuild=False):
    """Merge the shot list with the script's scenes. Only start_sec/end_sec
    (and an empty narration_summary) are written into existing rows; every
    other field is kept. Rows of scenes no longer in the script get status
    "removed" (nothing else changes). A scene with several rows (split into
    shots by hand) keeps its own times. Extra columns are kept.
    Returns a summary dict."""
    path = shotlist_path(ctx, project)
    fresh = scripts.build_shotlist(ctx, project)
    header, rows = read_csv_table(path)
    columns = csv_columns(ctx.paths, "shotlist.csv", header, project.meta["brand"], project.language)
    summary = {"added": [], "retimed": [], "removed": [], "restored": [], "rebuilt": rebuild}
    if rebuild or not rows:
        for r in fresh:
            r["asset_id"] = ""
        write_csv(path, fresh, columns)
        summary["added"] = [r["scene"] for r in fresh]
        return summary

    before = [dict(r) for r in rows]
    by_scene = {}
    for row in rows:
        n = scene_number(row)
        if n is not None:
            by_scene.setdefault(n, []).append(row)
    script_scenes = {r["scene"]: r for r in fresh}
    for n, new in script_scenes.items():
        existing = by_scene.get(n)
        if not existing:
            rows.append({**{c: "" for c in columns}, **{k: str(v) for k, v in new.items()}})
            summary["added"].append(n)
            continue
        for row in existing:
            if status(row) == REMOVED:  # the scene is back in the script
                row["status"] = TODO
                summary["restored"].append(n)
            if not (row.get("narration_summary") or "").strip():
                row["narration_summary"] = new["narration_summary"]
        if len(existing) == 1:
            row = existing[0]
            times = {k: str(new[k]) for k in TIMING}
            if any((row.get(k) or "").strip() != v for k, v in times.items()):
                row.update(times)
                summary["retimed"].append(n)
    for n, existing in by_scene.items():
        if n not in script_scenes:
            for row in existing:
                if status(row) != REMOVED:
                    row["status"] = REMOVED
                    summary["removed"].append(n)
    order = {id(r): i for i, r in enumerate(rows)}
    rows.sort(key=lambda r: (scene_number(r) is None, scene_number(r) or 0, order[id(r)]))
    if rows != before or list(header) != list(columns):
        write_csv(path, rows, columns)
    return summary


# ------------------------------------------------------------ link

def link(ctx, project, scene, asset_id):
    """Set asset_id on the scene's row; fill `file` from the register only if
    it is empty. Nothing already entered is overwritten."""
    asset = assets.find_asset(ctx, asset_id)
    path = shotlist_path(ctx, project)
    header, rows = read_csv_table(path)
    try:
        number = int(str(scene).strip())
    except ValueError:
        raise FactoryError(f"Scene must be a number (got '{scene}')") from None
    candidates = [r for r in rows if scene_number(r) == number and status(r) != REMOVED]
    if not candidates:
        raise FactoryError(f"Scene {number} has no row in shotlist.csv. Run: python -m factory shots generate {project.id}")
    target = next((r for r in candidates if (r.get("asset_id") or "").strip().upper() in ("", asset["id"].upper())), None)
    if target is None:
        linked = ", ".join(sorted({r["asset_id"].strip() for r in candidates}))
        raise FactoryError(f"Scene {number} is already linked to {linked}. Edit shotlist.csv to change it "
                           "(entered values are never overwritten)")
    target["asset_id"] = asset["id"]
    filled = False
    if not (target.get("file") or "").strip():
        target["file"] = asset["file"]
        filled = True
    write_csv(path, rows, csv_columns(ctx.paths, "shotlist.csv", header, project.meta["brand"], project.language))
    return asset, filled


# ------------------------------------------------------------ checks (plan §7)

def _past_visuals(ctx, project):
    ids = [s["id"] for s in ctx.config.stages]
    return project.stage in ids and ids.index(project.stage) > ids.index("visuals")


def _file_exists(ctx, project, value):
    value = value.strip().replace("\\", "/")
    return any((base / value).exists() for base in (project.folder, ctx.paths.assets, ctx.paths.root))


@register("visuals")
def check_shots(ctx, project):
    """Shot list rules (plan §7). A project already past Visuals (such as the
    Phase 1 sample) gets WARN instead of FAIL, as for Research (M2) and Fact
    Check (M5); the gate only ever checks the project's current stage."""
    findings = _shot_findings(ctx, project)
    if _past_visuals(ctx, project):
        findings = [f._replace(level=WARN, message=f.message + " (project is already past Visuals)")
                    if f.level == FAIL else f for f in findings]
    return findings


def _shot_findings(ctx, project):
    limits, self_made = rules(ctx)
    path = shotlist_path(ctx, project)
    if not path.exists():
        return [Finding(FAIL, "SHOTS_MISSING", "shotlist.csv is missing; create it with: "
                        f"python -m factory shots generate {project.id}", FILE)]
    header, rows = read_csv_table(path)
    if "scene" not in header:
        return [Finding(FAIL, "SHOTS_FILE", "shotlist.csv has no 'scene' column; rebuild it with: "
                        f"python -m factory shots generate {project.id} --force", FILE)]
    register_rows = {a["id"].strip().upper(): a for a in assets.list_assets(ctx) if (a.get("id") or "").strip()}
    script_scenes = [r["scene"] for r in scripts.build_shotlist(ctx, project)]
    active = [r for r in rows if status(r) != REMOVED]
    findings = []

    covered = {scene_number(r) for r in active}
    for n in script_scenes:
        if n not in covered:
            findings.append(Finding(FAIL, "SHOT_MISSING_SCENE", f"scene {n} has no row; run: "
                                    f"python -m factory shots generate {project.id}", FILE))
    for r in rows:
        n = scene_number(r)
        if status(r) == REMOVED:
            findings.append(Finding(WARN, "SHOT_REMOVED", f"scene {r.get('scene', '').strip()} is no longer in the "
                                    "script (status 'removed'); delete the row when you no longer need it", FILE))
        elif n is None or n not in script_scenes:
            findings.append(Finding(WARN, "SHOT_UNKNOWN_SCENE", f"row for scene '{r.get('scene', '').strip()}' "
                                    f"doesn't match a script scene; run: python -m factory shots generate {project.id}",
                                    FILE))
    not_done = [r.get("scene", "").strip() or "?" for r in active if status(r) != DONE]
    if not_done:
        findings.append(Finding(FAIL, "SHOT_NOT_DONE", "row(s) not 'done': scene " + ", ".join(not_done), FILE))

    for r in active:
        label = f"scene {r.get('scene', '').strip() or '?'}"
        asset_id = (r.get("asset_id") or "").strip().upper()
        asset = register_rows.get(asset_id) if asset_id else None
        if asset_id and asset is None:
            findings.append(Finding(FAIL, "SHOT_UNKNOWN_ASSET", f"{label}: asset {asset_id} is not in "
                                    "assets/register.csv", FILE))
        source = (r.get("source") or "").strip() or ((asset or {}).get("source") or "").strip()
        licence = (r.get("license") or "").strip() or ((asset or {}).get("license") or "").strip()
        if source and source.lower() not in self_made and not licence:
            where = f" (linked asset {asset_id} has none either)" if asset else ""
            findings.append(Finding(FAIL, "SHOT_NO_LICENSE", f"{label}: external source '{source}' has no "
                                    f"licence{where}", FILE))
        file = (r.get("file") or "").strip()
        if file and not _file_exists(ctx, project, file):
            findings.append(Finding(WARN, "SHOT_FILE_MISSING", f"{label}: file '{file}' not found locally "
                                    "(media isn't stored in git)", FILE))

    timed = []
    for r in active:
        start, end = _number(r.get("start_sec")), _number(r.get("end_sec"))
        label = f"scene {r.get('scene', '').strip() or '?'}"
        if start is None or end is None or end < start:
            findings.append(Finding(WARN, "SHOT_TIME", f"{label}: start/end times are missing or invalid", FILE))
            continue
        timed.append((start, end, label))
        limit = limits.get(project.meta["format"])
        if limit and end - start > limit:
            findings.append(Finding(WARN, "SHOT_TOO_LONG", f"{label} lasts {end - start:g} s; "
                                    f"{project.meta['format']}-form shots should be at most {limit:g} s", FILE))
    timed.sort()
    previous_end, previous = 0.0, "the start"
    for start, end, label in timed:
        if start > previous_end:
            findings.append(Finding(WARN, "SHOT_GAP", f"gap of {start - previous_end:g} s between "
                                    f"{previous} and {label}", FILE))
        elif start < previous_end:
            findings.append(Finding(WARN, "SHOT_OVERLAP", f"{label} starts {previous_end - start:g} s before "
                                    f"{previous} ends", FILE))
        previous_end, previous = max(previous_end, end), label
    order = {FAIL: 0, WARN: 1}
    return sorted(findings, key=lambda f: order.get(f.level, 2))


# ------------------------------------------------------------ commands

def run_generate(ctx, project, rebuild):
    s = generate(ctx, project, rebuild)
    path = display_path(shotlist_path(ctx, project), ctx.paths.root)
    if s["rebuilt"]:
        print(f"Wrote {len(s['added'])} scenes to {path}")
        return 0
    changes = [(s["added"], "added"), (s["retimed"], "times refreshed"),
               (s["removed"], "marked 'removed' (no longer in the script)"),
               (s["restored"], "back in the script (status set to 'todo')")]
    if not any(scenes for scenes, _ in changes):
        print(f"{path} already matches the script. Nothing changed.")
        return 0
    print(f"Updated {path} (rows you filled in are kept):")
    for scenes, what in changes:
        if scenes:
            print(f"  scene {', '.join(str(n) for n in scenes)}: {what}")
    return 0


def cmd_generate(args, ctx):
    return run_generate(ctx, find_project(ctx, args.project), args.force)


def cmd_link(args, ctx):
    p = find_project(ctx, args.project)
    asset, filled = link(ctx, p, args.scene, args.asset)
    print(f"Scene {args.scene} linked to {asset['id']} ({asset['file']}, licence: {asset['license'] or 'none recorded'})"
          + (" and its file filled in." if filled else "."))
    return 0


def cmd_check(args, ctx):
    p = find_project(ctx, args.project)
    findings = check_shots(ctx, p)
    for f in findings:
        print(f"  {format_finding(f)}")
    fails = sum(f.level == FAIL for f in findings)
    print("Shot list OK." if not findings else f"{fails} FAIL, {len(findings) - fails} WARN.")
    return 1 if fails else 0


def register(sub):
    p = sub.add_parser("shots", help="Shot List Generator: merge shot lists, link assets, check shots")
    s = p.add_subparsers(metavar="action", required=True)
    g = s.add_parser("generate", help="merge shotlist.csv with the script (keeps rows you filled in)")
    g.add_argument("project")
    g.add_argument("--force", action="store_true", help="rebuild from scratch (filled-in rows are lost)")
    g.set_defaults(func=cmd_generate)
    ln = s.add_parser("link", help="link a scene's row to an asset in assets/register.csv")
    ln.add_argument("project")
    ln.add_argument("scene")
    ln.add_argument("--asset", required=True, help="asset ID, e.g. AS0001")
    ln.set_defaults(func=cmd_link)
    ck = s.add_parser("check", help="check the shot list (changes nothing)")
    ck.add_argument("project")
    ck.set_defaults(func=cmd_check)
