"""Module 8: Analytics. Per-project performance logs (10_analytics/performance.csv) and reports."""

from collections import defaultdict

from factory.core.config import FactoryError
from factory.core.files import read_csv, read_csv_table, today, write_csv
from factory.core.options import add_brand, add_language, brand_id
from factory.core.projects import find_project, iter_projects
from factory.core.templates import csv_columns
from factory.core.validation import check_number, check_platform

NUMERIC = ("views", "watch_time_hours", "likes", "comments", "shares", "subscribers_gained")


def perf_path(ctx, project):
    return project.stage_dir(ctx, "analytics") / "performance.csv"


LIMITS = {"ctr_percent": 100}  # every metric must be >= 0; these also have a maximum
FLAGS = {"views": "views", "watch_time_hours": "watch-hours", "avg_view_duration_sec": "avg-view-sec",
         "ctr_percent": "ctr", "likes": "likes", "comments": "comments", "shares": "shares",
         "subscribers_gained": "subs", "days_since_publish": "days"}


def add_snapshot(ctx, project, platform, **metrics):
    """Log metrics for a platform the project has actually been published on."""
    platform = check_platform(ctx, platform)
    published = {pub["platform"] for pub in project.meta.get("publications", [])}
    if platform not in published:
        known = ", ".join(sorted(published)) or "none yet"
        raise FactoryError(f"{project.id} has no publication recorded on '{platform}' "
                           f"(recorded: {known}). Record it first with: publish record")
    for name, value in metrics.items():
        if isinstance(value, (int, float)):
            check_number(FLAGS.get(name, name), value, 0, LIMITS.get(name))
    path = perf_path(ctx, project)
    header, rows = read_csv_table(path)
    fields = csv_columns(ctx.paths, "performance.csv", header, project.meta["brand"], project.language)
    values = {k: v for k, v in metrics.items() if v is not None}
    unknown = [k for k in values if k not in fields]
    if unknown:  # never drop a value silently
        raise FactoryError(f"performance.csv has no column for: {', '.join(unknown)}")
    row = {f: "" for f in fields}
    row.update({"date_recorded": today(), "platform": platform})
    row.update(values)
    write_csv(path, rows + [row], fields)
    return row


def latest_snapshots(ctx, project):
    """Most recent row per platform (rows are appended over time)."""
    latest = {}
    for row in read_csv(perf_path(ctx, project)):
        if row.get("platform"):  # rows without a platform can't be attributed
            latest[row["platform"]] = row
    return latest


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def report(ctx, brand, language=None):
    by_project, by_division, by_language = [], defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for p in iter_projects(ctx, brand=brand, language=language):
        snaps = latest_snapshots(ctx, p)
        if not snaps:
            continue
        totals = {k: sum(num(s.get(k)) for s in snaps.values()) for k in NUMERIC}
        by_project.append({"id": p.id, "language": p.language, "division": p.meta["division"], **totals})
        for k, v in totals.items():
            by_division[p.meta["division"]][k] += v
            by_language[p.language][k] += v
    return {"projects": by_project, "divisions": dict(by_division), "languages": dict(by_language)}


def cmd_add(args, ctx):
    p = find_project(ctx, args.project)
    add_snapshot(ctx, p, args.platform, views=args.views, watch_time_hours=args.watch_hours,
                 avg_view_duration_sec=args.avg_view_sec, ctr_percent=args.ctr, likes=args.likes,
                 comments=args.comments, shares=args.shares, subscribers_gained=args.subs,
                 days_since_publish=args.days, notes=args.notes)
    print(f"Logged {args.platform} snapshot for {p.id}")
    return 0


def cmd_report(args, ctx):
    r = report(ctx, brand_id(args, ctx), args.lang)
    if not r["projects"]:
        print("No performance data yet. Log some with: python -m factory analytics add ...")
        return 0
    print(f"{'PROJECT':<48} {'VIEWS':>9} {'LIKES':>7} {'SUBS':>6}")
    for p in sorted(r["projects"], key=lambda p: p["views"], reverse=True):
        print(f"{p['id']:<48} {p['views']:>9.0f} {p['likes']:>7.0f} {p['subscribers_gained']:>6.0f}")
    print("\nBy division:")
    for d, t in sorted(r["divisions"].items(), key=lambda x: -x[1]["views"]):
        print(f"  {d:<20} {t['views']:>9.0f} views")
    print("By language:")
    for lang, t in r["languages"].items():
        print(f"  {lang:<20} {t['views']:>9.0f} views")
    return 0


def register(sub):
    p = sub.add_parser("analytics", help="Analytics: log performance and report")
    s = p.add_subparsers(metavar="action", required=True)
    a = s.add_parser("add", help="log a performance snapshot")
    a.add_argument("project")
    a.add_argument("--platform", required=True)
    a.add_argument("--views", type=int)
    a.add_argument("--watch-hours", type=float)
    a.add_argument("--avg-view-sec", type=float)
    a.add_argument("--ctr", type=float, help="click-through rate in percent")
    a.add_argument("--likes", type=int)
    a.add_argument("--comments", type=int)
    a.add_argument("--shares", type=int)
    a.add_argument("--subs", type=int, help="subscribers gained")
    a.add_argument("--days", type=int, help="days since publish")
    a.add_argument("--notes", default="")
    a.set_defaults(func=cmd_add)
    r = s.add_parser("report", help="totals by project, division and language")
    add_brand(r)
    add_language(r)
    r.set_defaults(func=cmd_report)
