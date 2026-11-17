"""Module 2: Niche Manager. Content divisions and how they are used."""

from collections import Counter

from factory.core.config import FactoryError
from factory.core.options import add_brand, brand_id
from factory.core.projects import iter_projects


def division_summary(ctx, brand):
    enabled = ctx.config.brand(brand)["divisions"]
    counts = Counter((p.meta["division"], p.language) for p in iter_projects(ctx, brand=brand))
    rows = []
    for div_id, div in ctx.config.divisions.items():
        rows.append({
            "id": div_id,
            "name": div["name"],
            "name_ms": div["name_ms"],
            "enabled": div_id in enabled,
            "projects": {lang: counts[(div_id, lang)] for lang in ctx.config.languages},
        })
    return rows


def cmd_list(args, ctx):
    brand = brand_id(args, ctx)
    langs = list(ctx.config.languages)
    print(f"{'DIVISION ID':<20} {'NAME':<22} {'NAMA (MS)':<26} " + " ".join(f"{l.upper():>3}" for l in langs))
    for row in division_summary(ctx, brand):
        flag = "" if row["enabled"] else "  (disabled for brand)"
        counts = " ".join(f"{row['projects'][l]:>3}" for l in langs)
        print(f"{row['id']:<20} {row['name']:<22} {row['name_ms']:<26} {counts}{flag}")
    return 0


def cmd_show(args, ctx):
    div = ctx.config.divisions.get(args.division)
    if not div:
        raise FactoryError(f"Unknown division '{args.division}'")
    style = ctx.config.visual_styles.get(div["visual_style"], {})
    print(f"{div['name']} / {div['name_ms']}  ({args.division})")
    print(f"  {div['description']}")
    print(f"  Visual style: {div['visual_style']}: {style.get('description', '')}")
    print(f"  Music mood  : {style.get('music_mood', '')}")
    print(f"  Rules       : {div['notes']}")
    return 0


def register(sub):
    p = sub.add_parser("niches", help="Niche Manager: content divisions")
    add_brand(p)
    p.set_defaults(func=cmd_list)
    s = p.add_subparsers(metavar="action")
    ls = s.add_parser("list", help="list divisions with project counts")
    add_brand(ls)
    ls.set_defaults(func=cmd_list)
    sh = s.add_parser("show", help="details and rules for one division")
    sh.add_argument("division")
    sh.set_defaults(func=cmd_show)
