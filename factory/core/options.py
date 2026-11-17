"""Shared CLI option helpers."""

from factory.core.config import FactoryError


def add_brand(parser):
    parser.add_argument("--brand", help="brand id (default from config/settings.json)")


def add_language(parser, required=False):
    parser.add_argument("--lang", required=required,
                        help="content language: en or ms")


def add_division(parser, required=False):
    parser.add_argument("--division", required=required, help="division id, see: niches")


def check_brand(ctx, brand):
    if brand is not None and brand not in ctx.config.brand_ids():
        known = ", ".join(ctx.config.brand_ids()) or "(none)"
        raise FactoryError(f"Unknown brand '{brand}'. Use one of: {known} "
                           "(each brand is a folder in brands/ with a brand.json)")
    return brand


def brand_id(args, ctx):
    return getattr(args, "brand", None) or ctx.config.settings["default_brand"]


def check_language(ctx, language):
    if language is not None and language not in ctx.config.languages:
        names = ", ".join(f"{code} ({info['name']})" for code, info in ctx.config.languages.items())
        raise FactoryError(f"Unknown language '{language}'. Use one of: {names}")
    return language


def check_division(ctx, division, brand=None):
    if division is None:
        return division
    if division not in ctx.config.divisions:
        raise FactoryError(f"Unknown division '{division}'. Choose: {', '.join(ctx.config.divisions)} "
                           "(see: python -m factory niches)")
    if brand and division not in ctx.config.brand(brand)["divisions"]:
        raise FactoryError(f"Division '{division}' is not enabled for brand '{brand}'")
    return division


def check_format(ctx, fmt):
    if fmt not in ctx.config.formats:
        raise FactoryError(f"Unknown format '{fmt}'. Choose: {', '.join(ctx.config.formats)}")
    return fmt
