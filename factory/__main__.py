"""Allows running the CLI with: python -m factory"""

import sys

# Checked before importing anything else, so older Pythons get a clear message
# instead of a syntax error. Keep this block free of newer syntax.
MIN_PYTHON = (3, 9)
if sys.version_info[:2] < MIN_PYTHON:
    sys.stderr.write(
        "QHAZE Faceless Content Factory needs Python %d.%d or newer; this is Python %d.%d.\n"
        "Install a newer Python from https://www.python.org/downloads/ and run it again.\n"
        % (MIN_PYTHON + tuple(sys.version_info[:2])))
    sys.exit(1)

from factory.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
