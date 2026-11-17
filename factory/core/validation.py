"""Validation for publishing and analytics input: platforms, URLs, dates, numbers.

Platforms and their web domains are defined in config/platforms.json.
"""

import re
from datetime import date
from urllib.parse import urlsplit

from factory.core.errors import FactoryError

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def check_platform(ctx, platform):
    """Return the platform id (case-insensitive input), or raise a clear error."""
    platforms = ctx.config.platforms
    key = (platform or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key not in platforms:
        raise FactoryError(f"Unknown platform '{platform}'. Use one of: {', '.join(platforms)}")
    return key


def check_url(ctx, url, platform):
    """The URL must be a full http(s) link on one of the platform's domains."""
    url = (url or "").strip()
    domains = ctx.config.platforms[platform]["domains"]
    example = f"https://www.{domains[0]}/..."
    if not url or any(c.isspace() for c in url):
        raise FactoryError(f"Invalid URL '{url}'. Paste the full link, e.g. {example}")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FactoryError(f"Invalid URL '{url}': it must start with https:// (e.g. {example})")
    host = (parts.hostname or "").lower()
    if not HOSTNAME.match(host):
        raise FactoryError(f"Invalid URL '{url}': '{host or '(empty)'}' is not a valid web address")
    if not any(host == d or host.endswith("." + d) for d in domains):
        label = ctx.config.platforms[platform]["label"]
        raise FactoryError(f"URL '{url}' is not a {label} link (expected a domain like "
                           f"{', '.join(domains)})")
    return url


def check_date(value):
    """YYYY-MM-DD, not in the future."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise FactoryError(f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-11-20") from None
    if parsed > date.today():
        raise FactoryError(f"Date {value} is in the future")
    return parsed.isoformat()


def check_number(name, value, minimum=0, maximum=None):
    if value is None:
        return None
    if value < minimum or (maximum is not None and value > maximum):
        limit = f"between {minimum} and {maximum}" if maximum is not None else f"{minimum} or more"
        raise FactoryError(f"--{name} must be {limit} (got {value})")
    return value
