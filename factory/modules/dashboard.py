"""Module 1: Dashboard. One-screen overview of the whole factory."""

from collections import Counter

from factory import __version__
from factory.core.options import add_brand, brand_id
from factory.core.projects import iter_projects
from factory.modules.assets import check_assets
from factory.modules.ideas import load_ideas
from factory.modules.production import stage_blockers


def overview(ctx, brand):
    projects = list(iter_projects(ctx, brand=brand))
    backlog = {lang: sum(1 for i in load_ideas(ctx, brand, lang) if i["status"] == "backlog")
               for lang in ctx.config.languages}
    return {
        "brand": ctx.config.brand(brand),
        "projects": projects,
        "by_stage": Counter(p.stage for p in projects),
        "by_language": Counter(p.language for p in projects),
        "by_division": Counter(p.meta["division"] for p in projects),
        "backlog": backlog,
        "forced": [p.id for p in projects if any(h.get("forced") for h in p.meta["history"])],
        "ready_to_advance": [p.id for p in projects
                             if p.stage != ctx.config.stages[-1]["id"] and not stage_blockers(ctx, p)],
        "asset_problems": len(check_assets(ctx)),
    }


def cmd_dashboard(args, ctx):
    o = overview(ctx, brand_id(args, ctx))
    b = o["brand"]
    print(f"QHAZE Faceless Content Factory v{__version__}")
    print(f"Brand: {b['name']}   Channels: " + ", ".join(f"{c['name']} ({c['language']})" for c in b["channels"]))
    print(f"\nProjects: {len(o['projects'])}   "
          + "   ".join(f"{ctx.config.languages[l]['name']}: {n}" for l, n in o["by_language"].items()))
    print("Ideas in backlog: " + ", ".join(f"{l.upper()} {n}" for l, n in o["backlog"].items()))
    print("\nPipeline:")
    for i, s in enumerate(ctx.config.stages, 1):
        n = o["by_stage"].get(s["id"], 0)
        print(f"  {i:>2}. {s['label']:<18} {'█' * n}{' ' if n else ''}{n}")
    if o["by_division"]:
        print("\nBy division:")
        for d, n in o["by_division"].most_common():
            print(f"  {ctx.config.divisions[d]['name']:<22} {n}")
    print("\nAttention:")
    print(f"  Ready to advance (checklist done): {', '.join(o['ready_to_advance']) or 'none'}")
    print(f"  Stages skipped with --force     : {', '.join(o['forced']) or 'none'}")
    print(f"  Asset register problems         : {o['asset_problems']}")
    return 0


def register(sub):
    p = sub.add_parser("dashboard", help="Dashboard: overview of everything")
    add_brand(p)
    p.set_defaults(func=cmd_dashboard)
