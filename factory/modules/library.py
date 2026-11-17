"""Module 5: Visual Library. Reusable visual styles per division."""

from factory.core.options import add_division


def cmd_visuals(args, ctx):
    divisions = ctx.config.divisions
    for div_id, div in divisions.items():
        if args.division and div_id != args.division:
            continue
        style = ctx.config.visual_styles[div["visual_style"]]
        print(f"{div['name']} → {div['visual_style']}")
        print(f"    look   : {style['description']}")
        print(f"    music  : {style['music_mood']}")
        print(f"    captions: {style['caption_style']}")
    return 0


def register(sub):
    p = sub.add_parser("library", help="Visual Library: visual styles per division")
    s = p.add_subparsers(metavar="action", required=True)
    vs = s.add_parser("visuals", help="visual styles per division")
    add_division(vs)
    vs.set_defaults(func=cmd_visuals)
