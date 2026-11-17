"""Very small template engine: replaces {{name}} placeholders with values."""

import re

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(text, values):
    """Replace {{key}} with values[key]; unknown keys are left untouched."""

    def replace(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return PLACEHOLDER.sub(replace, text)
