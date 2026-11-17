"""Command-line entry point: python -m factory <command> ...

Each software module registers its own commands, so new modules plug in by
adding them to MODULES. A future web UI would import the same module
functions instead of going through this file.
"""

import argparse
import sys

from factory import __version__
from factory.core.config import Context, FactoryError
from factory.core.errors import describe_os_error
from factory.core.options import check_brand, check_division, check_language
from factory.modules import (analytics, assets, dashboard, factcheck, ideas, library, niches,
                             planning, production, publishing, research, scripts)

MODULES = [dashboard, niches, ideas, research, planning, scripts, factcheck, library, production, publishing,
           analytics, assets]


def build_parser():
    parser = argparse.ArgumentParser(prog="factory", description="QHAZE Faceless Content Factory")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")
    for module in MODULES:
        module.register(sub)
    return parser


def safe_output_streams():
    """Never crash because the terminal or an output file can't show a character.

    On Windows, output redirected to a file or pipe uses the ANSI code page
    (e.g. cp1252), which has no ✔, ⚠ or Jawi letters. Such characters are
    replaced instead of raising UnicodeEncodeError. UTF-8 output is unaffected;
    for full Unicode in redirected output on Windows, set PYTHONUTF8=1."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if hasattr(stream, "reconfigure") and not encoding.startswith("utf"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):  # stream closed or not reconfigurable
                pass


def main(argv=None, ctx=None):
    safe_output_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        ctx = ctx or Context()
    except OSError as e:  # e.g. config/ can't be read
        print(f"Error: {describe_os_error(e)}", file=sys.stderr)
        return 1
    try:
        # Validate --brand, --lang and --division once for every command that
        # has them (case-insensitive), so a typo is an error, not an empty list.
        if getattr(args, "brand", None) is not None:
            args.brand = check_brand(ctx, args.brand.strip().lower())
        if getattr(args, "lang", None) is not None:
            args.lang = check_language(ctx, args.lang.strip().lower())
        if getattr(args, "division", None) is not None:
            brand = getattr(args, "brand", None) or ctx.config.settings["default_brand"]
            args.division = check_division(ctx, args.division.strip().lower(), brand)
        return args.func(args, ctx)
    except FactoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except OSError as e:  # permission denied, file locked, disk full...
        print(f"Error: {describe_os_error(e, ctx.paths.root)}", file=sys.stderr)
        return 1
    finally:
        for warning in ctx.warnings.values():
            print(f"Warning: {warning}", file=sys.stderr)
