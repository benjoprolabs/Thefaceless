"""Module 9: Asset Manager. Shared media library with a licence register (assets/register.csv)."""

import shutil
from pathlib import Path

from factory.core.config import FactoryError
from factory.core.files import append_csv, read_csv, today

FIELDS = ["id", "type", "file", "source", "license", "added", "notes"]
TYPES = ("music", "sfx", "broll", "images", "brand")


def list_assets(ctx, asset_type=None):
    rows = read_csv(ctx.paths.asset_register)
    return [r for r in rows if not asset_type or r["type"] == asset_type]


def add_asset(ctx, file, asset_type, source="", license="", notes=""):
    if asset_type not in TYPES:
        raise FactoryError(f"Type must be one of: {', '.join(TYPES)}")
    src = Path(file)
    if not src.is_file():
        raise FactoryError(f"File not found: {file}")
    dest = ctx.paths.assets / asset_type / src.name
    if dest.exists():
        raise FactoryError(f"Asset already exists: {dest.relative_to(ctx.paths.root)}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    existing = list_assets(ctx)
    row = {"id": f"AS{len(existing) + 1:04d}", "type": asset_type,
           "file": dest.relative_to(ctx.paths.assets).as_posix(), "source": source,
           "license": license, "added": today(), "notes": notes}
    append_csv(ctx.paths.asset_register, row, FIELDS)
    return row


def check_assets(ctx):
    """Problems: missing licence, missing file, or files not in the register."""
    problems = []
    registered = set()
    for r in list_assets(ctx):
        registered.add(r["file"])
        if not r["license"]:
            problems.append(f"{r['id']} {r['file']}: no licence recorded")
        if not (ctx.paths.assets / r["file"]).exists():
            problems.append(f"{r['id']} {r['file']}: file missing (media is not stored in git)")
    for t in TYPES:
        for f in sorted((ctx.paths.assets / t).glob("*")):
            rel = f.relative_to(ctx.paths.assets).as_posix()
            if f.is_file() and not f.name.startswith(".") and rel not in registered:
                problems.append(f"{rel}: not in register")
    return problems


def cmd_list(args, ctx):
    rows = list_assets(ctx, args.type)
    if not rows:
        print("No assets registered. Add one: python -m factory assets add FILE --type music --license ...")
    for r in rows:
        print(f"{r['id']}  {r['type']:<7} {r['file']:<40} {r['license'] or '(no licence)'}")
    return 0


def cmd_add(args, ctx):
    row = add_asset(ctx, args.file, args.type, args.source, args.license, args.notes)
    print(f"Registered {row['id']}: assets/{row['file']}")
    return 0


def cmd_check(args, ctx):
    problems = check_assets(ctx)
    for p in problems:
        print("  ! " + p)
    print("All assets OK." if not problems else f"{len(problems)} problem(s).")
    return 1 if problems else 0


def register(sub):
    p = sub.add_parser("assets", help="Asset Manager: shared media and licences")
    p.set_defaults(func=cmd_list, type=None)
    s = p.add_subparsers(metavar="action")
    ls = s.add_parser("list")
    ls.add_argument("--type", choices=TYPES)
    ls.set_defaults(func=cmd_list)
    ad = s.add_parser("add", help="copy a file into assets/ and register it")
    ad.add_argument("file")
    ad.add_argument("--type", required=True, choices=TYPES)
    ad.add_argument("--source", default="")
    ad.add_argument("--license", default="")
    ad.add_argument("--notes", default="")
    ad.set_defaults(func=cmd_add)
    s.add_parser("check", help="find missing licences and files").set_defaults(func=cmd_check)
