"""Module 7: Publishing Manager. Record where and when each video was published."""

from factory.core.config import FactoryError
from factory.core.files import today
from factory.core.options import add_brand, add_language, brand_id
from factory.core.projects import find_project, iter_projects

PLATFORMS = ("youtube", "youtube_shorts", "tiktok", "instagram_reels", "facebook", "facebook_reels")


def record_publication(ctx, project, platform, url, date=None):
    if platform not in PLATFORMS:
        raise FactoryError(f"Platform must be one of: {', '.join(PLATFORMS)}")
    if ctx.config.stage_index(project.stage) < ctx.config.stage_index("publish"):
        raise FactoryError("Project has not reached the Publishing stage yet.")
    pub = {"platform": platform, "url": url, "date": date or today()}
    project.meta.setdefault("publications", []).append(pub)
    project.save()
    return pub


def cmd_record(args, ctx):
    p = find_project(ctx, args.project)
    pub = record_publication(ctx, p, args.platform, args.url, args.date)
    print(f"Recorded {pub['platform']} on {pub['date']} for {p.id}")
    return 0


def cmd_list(args, ctx):
    brand = brand_id(args, ctx)
    publish_index = ctx.config.stage_index("publish")
    ready, published = [], []
    for p in iter_projects(ctx, brand=brand, language=args.lang):
        if p.meta.get("publications"):
            published.append(p)
        elif ctx.config.stage_index(p.stage) >= publish_index:
            ready.append(p)
    print("Ready to publish:")
    for p in ready:
        print(f"  {p.id} ({p.language})")
    print("Published:")
    for p in published:
        for pub in p.meta["publications"]:
            print(f"  {pub['date']}  {pub['platform']:<15} {p.id}  {pub['url']}")
    return 0


def register(sub):
    p = sub.add_parser("publish", help="Publishing Manager: publish queue and records")
    add_brand(p)
    add_language(p)
    p.set_defaults(func=cmd_list)
    s = p.add_subparsers(metavar="action")
    ls = s.add_parser("list")
    add_brand(ls)
    add_language(ls)
    ls.set_defaults(func=cmd_list)
    r = s.add_parser("record", help="record a publication")
    r.add_argument("project")
    r.add_argument("--platform", required=True, choices=PLATFORMS)
    r.add_argument("--url", required=True)
    r.add_argument("--date", help="YYYY-MM-DD (default today)")
    r.set_defaults(func=cmd_record)
