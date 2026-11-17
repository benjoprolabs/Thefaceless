"""Command-line entry point.

Usage:
    python -m factory info
    python -m factory stages
    python -m factory ideas
    python -m factory new "Video title" [--format short|long] [--idea IDEA-001]
    python -m factory status

Each command is a small function; add new ones by writing a function and
registering it in build_parser().
"""

import argparse

from factory import __version__
from factory.config import Paths, load_channel, load_stages
from factory.ideas import find_idea, load_ideas
from factory.projects import create_project, list_projects


def cmd_info(args, paths):
    channel = load_channel(paths)
    print(f"QHAZE Faceless Content Factory v{__version__}")
    print(f"Channel : {channel['channel_name']} ({channel['niche']})")
    print(f"Root    : {paths.root}")
    print(f"Ideas   : {len(load_ideas(paths))}")
    print(f"Projects: {len(list_projects(paths))}")
    return 0


def cmd_stages(args, paths):
    for i, stage in enumerate(load_stages(paths), 1):
        folder = stage["folder"] or "-"
        print(f"{i}. {stage['label']:<22} id={stage['id']:<10} folder={folder}")
    return 0


def cmd_ideas(args, paths):
    ideas = load_ideas(paths)
    if not ideas:
        print("No ideas yet. Add rows to ideas/ideas.csv.")
        return 0
    print(f"{'ID':<10} {'SCORE':>5}  {'STATUS':<14} TITLE")
    for idea in sorted(ideas, key=lambda i: float(i["score"] or 0), reverse=True):
        print(f"{idea['id']:<10} {idea['score']:>5}  {idea['status']:<14} {idea['title']}")
    return 0


def cmd_new(args, paths):
    title, fmt = args.title, args.format
    if args.idea:
        idea = find_idea(paths, args.idea)
        if idea is None:
            print(f"Error: idea '{args.idea}' not found in ideas/ideas.csv")
            return 1
        title = title or idea["title"]
        fmt = fmt or idea["format"] or None
    if not title:
        print("Error: give a title, or --idea IDEA-ID")
        return 1
    try:
        folder = create_project(paths, title, fmt=fmt, idea_id=args.idea or "")
    except (ValueError, FileExistsError) as e:
        print(f"Error: {e}")
        return 1
    print(f"Created project: {folder.relative_to(paths.root)}")
    print("Next step: fill in 01_research/idea.md")
    return 0


def cmd_status(args, paths):
    projects = list_projects(paths)
    if not projects:
        print("No projects yet. Create one with: python -m factory new \"My title\"")
        return 0
    labels = {s["id"]: s["label"] for s in load_stages(paths)}
    print(f"{'PROJECT':<45} {'FORMAT':<6} STAGE")
    for p in projects:
        print(f"{p['id']:<45} {p['format']:<6} {labels.get(p['stage'], p['stage'])}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="factory", description="QHAZE Faceless Content Factory")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    sub.add_parser("info", help="show channel and factory summary").set_defaults(func=cmd_info)
    sub.add_parser("stages", help="list pipeline stages").set_defaults(func=cmd_stages)
    sub.add_parser("ideas", help="list the idea backlog by score").set_defaults(func=cmd_ideas)

    new = sub.add_parser("new", help="create a new video project")
    new.add_argument("title", nargs="?", help="video title")
    new.add_argument("--format", help="short or long (see config/channel.json)")
    new.add_argument("--idea", help="idea ID from ideas/ideas.csv")
    new.set_defaults(func=cmd_new)

    sub.add_parser("status", help="show all projects and their stage").set_defaults(func=cmd_status)
    return parser


def main(argv=None, paths=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args, paths or Paths())
