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
    return render(path.read_text(encoding="utf-8"), values)
