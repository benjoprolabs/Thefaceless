"""Template rendering and lookup.

Placeholders look like {{name}}. Templates are resolved with overrides, most
specific first, so a brand or language can customise any template:

    brands/<brand>/templates/<lang>/<name>
    brands/<brand>/templates/<name>
    templates/<lang>/<name>
    templates/<name>
"""

import re

from factory.core.config import FactoryError
from factory.core.files import csv_header, read_text

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(text, values):
    """Replace {{key}} with values[key]; unknown keys are left untouched."""

    def replace(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return PLACEHOLDER.sub(replace, text)


def find_template(paths, name, brand=None, language=None):
    candidates = []
    if brand:
        base = paths.brand_dir(brand) / "templates"
        if language:
            candidates.append(base / language / name)
        candidates.append(base / name)
    if language:
        candidates.append(paths.templates / language / name)
    candidates.append(paths.templates / name)
    for c in candidates:
        if c.exists():
            return c
    raise FactoryError(f"Template not found: {name}")


def render_template(paths, name, values, brand=None, language=None):
    path = find_template(paths, name, brand, language)
    return render(read_text(path), values)


def csv_columns(paths, name, existing_header=(), brand=None, language=None):
    """Columns for a project CSV (e.g. performance.csv, shotlist.csv).

    The template defines the standard columns, so a CSV that was deleted,
    emptied or had columns removed can be rebuilt without losing data. Any
    extra columns the user added to the existing file are kept, in order."""
    columns = csv_header(find_template(paths, name, brand, language))
    return columns + [c for c in existing_header if c and c not in columns]
