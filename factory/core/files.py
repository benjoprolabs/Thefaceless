"""Small file helpers shared by all modules."""

import csv
import hashlib
import json
import os
import re
from datetime import date


def today():
    return date.today().isoformat()


def slugify(text, max_len=50):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "untitled"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if private:
        make_private(path)


def make_private(path):
    """Owner-only permissions (no effect on Windows)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path, row, fieldnames):
    exists = path.exists() and path.stat().st_size > 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def csv_header(path):
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


UNCHECKED = re.compile(r"^\s*[-*]\s+\[ \]\s+(.*)$", re.MULTILINE)


def unchecked_items(text):
    """Return the text of every unticked '- [ ]' checklist item."""
    return [m.strip() for m in UNCHECKED.findall(text)]
