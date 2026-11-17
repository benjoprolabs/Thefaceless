"""Command-line entry point: python -m factory <command> ...

Each software module registers its own commands, so new modules plug in by
adding them to MODULES. A future web UI would import the same module
functions instead of going through this file.
"""

import argparse
import sys

from factory import __version__
from factory.core.config import Context, FactoryError
from factory.core.options import check_language
from factory.modules import (analytics, assets, dashboard, ideas, library, niches,
                             production, publishing, scripts)

MODULES = [dashboard, niches, ideas, scripts, library, production, publishing,
           analytics, assets]


def build_parser():
    parser = argparse.ArgumentParser(prog="factory", description="QHAZE Faceless Content Factory")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")
    for module in MODULES:
        module.register(sub)
    return parser


def main(argv=None, ctx=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    ctx = ctx or Context()
    try:
        # Validate --lang once for every command that has it (EN → en).
        if getattr(args, "lang", None) is not None:
            args.lang = check_language(ctx, args.lang.strip().lower())
        return args.func(args, ctx)
    except FactoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        for warning in ctx.warnings.values():
            print(f"Warning: {warning}", file=sys.stderr)
