"""Module 4: Script Studio. Parse scripts, check length, claims and fact-check coverage."""

import csv
import io
import re

from factory.core.files import csv_header
from factory.core.config import FactoryError
from factory.core.projects import find_project

SCENE = re.compile(r"^##\s*\[SCENE\s+(\d+)\]\s*(.*)$")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
CLAIM = re.compile(r"\[F(\d+)\]")


def parse_scenes(text):
    """Return [{'number', 'title', 'narration'}] from a script. Only text under [SCENE] headings counts."""
    text = COMMENT.sub("", text)
    scenes, current = [], None
    for line in text.splitlines():
        m = SCENE.match(line.strip())
        if m:
            current = {"number": int(m.group(1)), "title": m.group(2).strip(), "lines": []}
            scenes.append(current)
        elif line.startswith("#"):
            current = None  # any other heading ends narration
        elif current is not None and line.strip():
            current["lines"].append(line.strip())
    return [{"number": s["number"], "title": s["title"], "narration": " ".join(s["lines"])}
            for s in scenes]


def spoken_text(narration):
    """Narration without claim markers (the words to be spoken)."""
    return re.sub(r"\s+", " ", re.sub(r"\s*\[F\d+\]", "", narration)).strip()


def word_count(text):
    return len(re.findall(r"\b[\w'-]+\b", text))


def script_path(ctx, project):
    return project.stage_dir(ctx, "script") / "script.md"


def project_narration(ctx, project):
    return "\n\n".join(spoken_text(s["narration"]) for s in
                       parse_scenes(script_path(ctx, project).read_text(encoding="utf-8")))


def analyse(ctx, project):
    text = script_path(ctx, project).read_text(encoding="utf-8")
    scenes = parse_scenes(text)
    wpm = ctx.config.languages[project.language]["words_per_minute"]
    spec = ctx.config.formats[project.meta["format"]]
    words = sum(word_count(spoken_text(s["narration"])) for s in scenes)
    seconds = round(words / wpm * 60)
    claims = sorted({int(n) for s in scenes for n in CLAIM.findall(s["narration"])})
    factcheck = (project.stage_dir(ctx, "factcheck") / "factcheck.md").read_text(encoding="utf-8")
    checked = {int(n) for n in re.findall(r"^\|\s*F(\d+)\s*\|\s*[^|\s]", factcheck, re.MULTILINE)}
    return {
        "scenes": len(scenes),
        "empty_scenes": [s["number"] for s in scenes if not s["narration"]],
        "words": words,
        "seconds": seconds,
        "target_seconds": project.meta["target_seconds"],
        "min_seconds": spec["min_seconds"],
        "max_seconds": spec["max_seconds"],
        "in_range": spec["min_seconds"] <= seconds <= spec["max_seconds"],
        "claims": claims,
        "unchecked_claims": [c for c in claims if c not in checked],
    }


def build_shotlist(ctx, project):
    """Shot list rows from script scenes, timed by word count."""
    wpm = ctx.config.languages[project.language]["words_per_minute"]
    text = script_path(ctx, project).read_text(encoding="utf-8")
    rows, start = [], 0.0
    for s in parse_scenes(text):
        dur = word_count(spoken_text(s["narration"])) / wpm * 60
        rows.append({"scene": s["number"], "start_sec": round(start), "end_sec": round(start + dur),
                     "narration_summary": s["title"], "visual_type": "", "visual_description": "",
                     "source": "", "license": "", "file": "", "status": "todo"})
        start += dur
    return rows


def cmd_check(args, ctx):
    p = find_project(ctx, args.project)
    r = analyse(ctx, p)
    ok = "OK" if r["in_range"] else "OUT OF RANGE"
    print(f"Scenes: {r['scenes']}   Words: {r['words']}   Estimated: {r['seconds']} s "
          f"(target {r['target_seconds']} s, allowed {r['min_seconds']}–{r['max_seconds']} s) → {ok}")
    if r["empty_scenes"]:
        print(f"Empty scenes: {r['empty_scenes']}")
    print(f"Claims marked: {', '.join('F%d' % c for c in r['claims']) or 'none'}")
    if r["unchecked_claims"]:
        print("Claims missing from factcheck.md: " + ", ".join(f"F{c}" for c in r["unchecked_claims"]))
    problems = (not r["in_range"]) or r["empty_scenes"] or r["unchecked_claims"]
    return 1 if problems else 0


def cmd_text(args, ctx):
    print(project_narration(ctx, find_project(ctx, args.project)))
    return 0


def cmd_shotlist(args, ctx):
    p = find_project(ctx, args.project)
    path = p.stage_dir(ctx, "visuals") / "shotlist.csv"
    existing = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    if len(existing) > 1 and not args.force:
        raise FactoryError("shotlist.csv already has rows. Use --force to overwrite.")
    rows = build_shotlist(ctx, p)
    fields = csv_header(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} scenes to {path.relative_to(ctx.paths.root)}")
    return 0


def register(sub):
    p = sub.add_parser("script", help="Script Studio: check scripts and build shot lists")
    s = p.add_subparsers(metavar="action", required=True)
    c = s.add_parser("check", help="length, empty scenes and fact-check coverage")
    c.add_argument("project")
    c.set_defaults(func=cmd_check)
    t = s.add_parser("text", help="print the narration only (for recording or reading aloud)")
    t.add_argument("project")
    t.set_defaults(func=cmd_text)
    sl = s.add_parser("shotlist", help="create shot list rows from script scenes")
    sl.add_argument("project")
    sl.add_argument("--force", action="store_true")
    sl.set_defaults(func=cmd_shotlist)
