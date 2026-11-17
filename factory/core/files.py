"""Small file helpers shared by all modules."""

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import date

from factory.core.errors import FactoryError


def today():
    return date.today().isoformat()


# Letters that Unicode does not decompose into "base letter + accent".
EXTRA_LATIN = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
                             "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "TH", "ð": "d",
                             "ı": "i", "ŋ": "ng"})


def _to_ascii(char):
    """'é' → 'e', 'ß' → 'ss'; characters with no Latin equivalent → ''."""
    decomposed = unicodedata.normalize("NFKD", char.translate(EXTRA_LATIN))
    return "".join(c for c in decomposed if c.isascii())


def slugify(text, max_len=50):
    """ASCII slug: accents removed ('Café crème' → 'cafe-creme'). Returns
    'untitled' if nothing is left; use title_slug() for project IDs."""
    ascii_text = "".join(_to_ascii(c) for c in text)
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "untitled"


def title_slug(title, max_len=50):
    """Slug for a project ID that keeps different titles apart.

    Latin titles (with or without accents) become a readable slug. If the
    title has letters or digits that can't be written in Latin letters (Jawi,
    Arabic, Chinese...), a short fingerprint of the full title is added, e.g.
    'jawi-3f9a2c' or 'sejarah-3f9a2c', so two different titles never get the
    same slug. The same title always gives the same slug."""
    title = unicodedata.normalize("NFC", title.strip())
    untranslatable = [c for c in title if unicodedata.category(c)[0] in "LN" and not _to_ascii(c).strip()]
    slug = slugify(title, max_len)
    if not untranslatable and slug != "untitled":
        return slug
    tag = hashlib.sha1(title.casefold().encode("utf-8")).hexdigest()[:6]
    if slug != "untitled":
        return f"{slug[:max_len - 7].rstrip('-')}-{tag}"
    script = "jawi" if any(unicodedata.name(c, "").startswith("ARABIC") for c in untranslatable) else "title"
    return f"{script}-{tag}"


def read_json(path):
    """Parse a JSON file. Any text encoding is accepted (see read_text);
    invalid JSON raises json.JSONDecodeError."""
    return json.loads(read_text(path))


def write_new_text(path, text):
    """Write a new text file (e.g. from a template) with one native line ending
    per line. Templates checked out on Windows have CRLF; writing them as-is in
    text mode would give CR CR LF, so line endings are normalised first."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8")


def write_text_exact(path, text):
    """Rewrite an existing text file keeping its own line endings exactly
    (no newline translation on any platform)."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- CSV
# CSV files are often opened and re-saved in Excel, which can add a hidden
# byte-order mark (BOM), save in a Windows encoding, use ";" as the separator
# (common with Malaysian/European regional settings), pad headers with spaces
# or leave blank rows. Reading tolerates all of these; writing always produces
# standard UTF-8, comma-separated files.

def _decode(raw):
    """UTF-8 (with or without BOM), else Windows-1252, else Latin-1 (never fails)."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_text(path):
    """Read a Markdown/text file written by any editor (e.g. Windows Notepad
    "ANSI" files are cp1252). Never raises UnicodeDecodeError."""
    return _decode(path.read_bytes())


def _delimiter(first_line):
    return ";" if first_line.count(";") > first_line.count(",") else ","


def read_csv_table(path):
    """Return (fieldnames, rows) from a CSV, tolerating Excel quirks."""
    if not path.exists():
        return [], []
    text = _decode(path.read_bytes())
    lines = text.splitlines()
    first = next((line for line in lines if line.strip()), "")
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(first))
    table = [row for row in reader if any(cell.strip() for cell in row)]
    if not table:
        return [], []
    header = [h.strip() for h in table[0]]
    rows = []
    for values in table[1:]:
        values = [v.strip() for v in values] + [""] * (len(header) - len(values))
        rows.append(dict(zip(header, values)))
    return header, rows


def read_csv(path):
    return read_csv_table(path)[1]


def csv_header(path):
    return read_csv_table(path)[0]


def require_columns(path, header, required):
    missing = [c for c in required if c not in header]
    if missing:
        raise FactoryError(f"{path.name} is missing column(s): {', '.join(missing)}. "
                           f"The first row must be: {','.join(required)}  ({path})")


def write_csv(path, rows, fieldnames):
    """Write standard UTF-8 CSV. Extra columns already in the rows are kept."""
    extra = [k for row in rows for k in row if k not in fieldnames]
    fieldnames = list(fieldnames) + list(dict.fromkeys(extra))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path, row, fieldnames):
    """Add a row. The whole file is rewritten, so an Excel-saved file is
    normalised instead of getting a row in a different format."""
    write_csv(path, read_csv(path) + [row], fieldnames)


def to_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


UNCHECKED = re.compile(r"^\s*[-*]\s+\[ \]\s+(.*)$", re.MULTILINE)
CHECKLIST_ITEM = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+", re.MULTILINE)


def unchecked_items(text):
    """Return the text of every unticked '- [ ]' checklist item."""
    return [m.strip() for m in UNCHECKED.findall(text)]


def has_checklist(text):
    """True if the text contains at least one '- [ ]' or '- [x]' item."""
    return bool(CHECKLIST_ITEM.search(text))
