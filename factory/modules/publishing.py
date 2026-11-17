"""Module 7: Publishing Manager. Record where and when each video was published."""

from factory.core.config import FactoryError
from factory.core.files import today
from factory.core.options import add_brand, add_language, brand_id
from factory.core.projects import find_project, iter_projects
from factory.core.validation import check_date, check_platform, check_url


def record_publication(ctx, project, platform, url, date=None):
    platform = check_platform(ctx, platform)
    url = check_url(ctx, url, platform)
    date = check_date(date) if date else today()
    if ctx.config.stage_index(project.stage) < ctx.config.stage_index("publish"):
        raise FactoryError("Project has not reached the Publishing stage yet.")
    for pub in project.meta.get("publications", []):
        if pub["url"].rstrip("/") == url.rstrip("/"):
            raise FactoryError(f"This URL is already recorded for {project.id} ({pub['platform']}, {pub['date']})")
    pub = {"platform": platform, "url": url, "date": date}
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
    r.add_argument("--platform", required=True, help="see config/platforms.json, e.g. youtube, tiktok")
    r.add_argument("--url", required=True, help="full link, e.g. https://www.youtube.com/watch?v=...")
    r.add_argument("--date", help="YYYY-MM-DD (default today)")
    r.set_defaults(func=cmd_record)
