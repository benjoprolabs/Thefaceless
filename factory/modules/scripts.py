"""Module 4: Script Writing Engine (Script Studio).

Phase 1: parse scripts, check length, claims and fact-check coverage.
Phase 2, M4 (v0.4.4):
  - `script scaffold` builds one [SCENE] per outline point of plan.md, only
    while the script's scene section is still the unedited template;
  - versions: `script snapshot`, `script versions`, `script diff`
    (03_script/versions/vN.md; compared with difflib);
  - per-scene timing at the language's speaking rate (languages.json);
  - Script checks from PHASE2_PLAN.md §7: hook length, sentence length, empty
    scenes, call to action in the last scene, Product & Affiliate spoken
    disclosure, Psychology sensitive terms. Thresholds: config/rules.json.
"""

import difflib
import re

from factory.core.files import read_csv_table, read_text, today, write_csv, write_text_exact
from factory.core.config import FactoryError
from factory.core.checks import FAIL, WARN, Finding, failures, format_finding, register
from factory.core.errors import display_path
from factory.core.projects import find_project
from factory.core.templates import csv_columns

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
                       parse_scenes(read_text(script_path(ctx, project))))


def scene_timing(scenes, wpm):
    """Per-scene [{'number', 'title', 'words', 'seconds', 'start', 'end'}] at `wpm`
    words per minute (seconds rounded to 0.1; start/end are running totals)."""
    rows, start = [], 0.0
    for s in scenes:
        words = word_count(spoken_text(s["narration"]))
        seconds = words / wpm * 60
        rows.append({"number": s["number"], "title": s["title"], "words": words,
                     "seconds": round(seconds, 1), "start": round(start, 1), "end": round(start + seconds, 1)})
        start += seconds
    return rows


def analyse(ctx, project):
    text = read_text(script_path(ctx, project))
    scenes = parse_scenes(text)
    wpm = ctx.config.languages[project.language]["words_per_minute"]
    spec = ctx.config.formats[project.meta["format"]]
    words = sum(word_count(spoken_text(s["narration"])) for s in scenes)
    seconds = round(words / wpm * 60)
    claims = sorted({int(n) for s in scenes for n in CLAIM.findall(s["narration"])})
    factcheck = read_text(project.stage_dir(ctx, "factcheck") / "factcheck.md")
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
        "words_per_minute": wpm,
        "timing": scene_timing(scenes, wpm),
    }


# ------------------------------------------------------------ checks
# The Phase 1 rules of `script check`, as findings used by the stage gates.

def _script_file(ctx, project, stage):
    return display_path(project.stage_dir(ctx, stage) / f"{stage}.md", project.folder)


DEFAULT_HOOK_MAX_SECONDS = {"short": 5, "long": 20}
DEFAULT_MAX_SENTENCE_WORDS = 25
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def script_rules(ctx):
    """M4 thresholds from config/rules.json "script" (defaults if a key is missing)."""
    cfg = ctx.config.rules["script"]
    hook = cfg.get("hook_max_seconds", {})
    if not isinstance(hook, dict):
        raise FactoryError("config/rules.json: script.hook_max_seconds must be like {\"short\": 5, \"long\": 20}")
    hook = {**DEFAULT_HOOK_MAX_SECONDS, **hook}
    sentence = cfg.get("max_sentence_words", DEFAULT_MAX_SENTENCE_WORDS)
    for name, value in [("max_sentence_words", sentence)] + [(f"hook_max_seconds.{k}", v) for k, v in hook.items()]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise FactoryError(f"config/rules.json: script.{name} must be a number above 0")
    phrases = {}
    for key in ("cta_phrases", "disclosure_phrases"):
        value = cfg.get(key, {})
        if not isinstance(value, dict) or not all(isinstance(v, list) for v in value.values()):
            raise FactoryError(f"config/rules.json: script.{key} must map each language to a list of phrases")
        phrases[key] = value
    return {"hook_max_seconds": hook, "max_sentence_words": sentence, **phrases}


def _phrase_found(text, phrases):
    """First phrase found in text as whole words (case-insensitive), or None."""
    found = _terms_found(text, phrases)
    return found[0] if found else None


def _terms_found(text, terms):
    """Whole-word matches of any term (case-insensitive), in list order, once each."""
    return [t for t in dict.fromkeys(str(t).strip() for t in terms)
            if t and re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, re.IGNORECASE)]


def sentences(text):
    return [s.strip() for s in SENTENCE_END.split(text) if s.strip()]


def _style_findings(ctx, project, r, scenes, file):
    """Plan §7 Script rules added in M4 (hook, sentences, call to action,
    disclosure, sensitive terms)."""
    rules = script_rules(ctx)
    fmt, lang = project.meta["format"], project.language
    division = ctx.config.divisions[project.meta["division"]]
    spoken = [(s["number"], spoken_text(s["narration"])) for s in scenes]
    written = [(n, t) for n, t in spoken if t]
    findings = []
    if not written:
        return findings
    first = r["timing"][0]
    limit = rules["hook_max_seconds"].get(fmt)
    if limit and first["words"] and first["seconds"] > limit:
        findings.append(Finding(WARN, "SCRIPT_HOOK", f"the hook (scene {first['number']}) takes about "
                                f"{first['seconds']} s; keep it under {limit} s for {fmt}-form", file))
    max_words = rules["max_sentence_words"]
    for number, text in written:
        for sentence in sentences(text):
            count = word_count(sentence)
            if count > max_words:
                start = " ".join(sentence.split()[:6])
                findings.append(Finding(WARN, "SCRIPT_SENTENCE", f"scene {number}: a sentence has {count} words "
                                        f"(max {max_words}): \"{start} …\"", file))
    last_number, last_text = spoken[-1]
    cta = rules["cta_phrases"].get(lang, [])
    if cta and last_text and not _phrase_found(last_text, cta):
        findings.append(Finding(WARN, "SCRIPT_CTA", f"no call to action in the last scene (scene {last_number}), "
                                "e.g. " + ", ".join(f"'{c}'" for c in cta[:3]), file))
    if division.get("disclosure_required"):
        phrases = rules["disclosure_phrases"].get(lang, [])
        if phrases and not any(_phrase_found(t, phrases) for _, t in written):
            findings.append(Finding(FAIL, "SCRIPT_DISCLOSURE", "no spoken disclosure in the narration "
                                    f"({division['name']} videos must say it, e.g. "
                                    + ", ".join(f"'{p}'" for p in phrases[:3]) + ")", file))
    terms = division.get("sensitive_terms", {})
    terms = terms.get(lang, []) if isinstance(terms, dict) else []
    for number, text in written:
        found = _terms_found(text, terms)
        if found:
            findings.append(Finding(WARN, "SCRIPT_SENSITIVE", f"scene {number} uses " + ", ".join(
                f"'{t}'" for t in found) + f": {division['notes']}", file))
    return findings


@register("script")
def check_script(ctx, project):
    tolerance = ctx.config.rules["script"]["target_tolerance_percent"] / 100  # read first: a broken
    script_rules(ctx)                                                          # rules.json always shows
    r = analyse(ctx, project)
    file = _script_file(ctx, project, "script")
    findings = []
    if r["scenes"] == 0:
        findings.append(Finding(FAIL, "SCRIPT_NO_SCENES", "the script has no [SCENE n] sections", file))
    for n in r["empty_scenes"]:
        findings.append(Finding(FAIL, "SCRIPT_EMPTY_SCENE", f"scene {n} has no narration", file))
    if r["scenes"] and not r["in_range"]:
        findings.append(Finding(FAIL, "SCRIPT_LENGTH",
                                f"estimated {r['seconds']} s is outside {r['min_seconds']}–{r['max_seconds']} s "
                                f"for {project.meta['format']}-form", file))
    else:
        target = r["target_seconds"]
        if r["scenes"] and target and abs(r["seconds"] - target) > target * tolerance:
            findings.append(Finding(WARN, "SCRIPT_TARGET",
                                    f"estimated {r['seconds']} s is more than {round(tolerance * 100)}% "
                                    f"from the {target} s target", file))
    scenes = parse_scenes(read_text(script_path(ctx, project)))
    return findings + _style_findings(ctx, project, r, scenes, file)


@register("factcheck")
def check_claims_covered(ctx, project):
    r = analyse(ctx, project)
    file = _script_file(ctx, project, "factcheck")
    return [Finding(FAIL, "FACTCHECK_MISSING_CLAIM", f"claim F{n} from the script has no row in factcheck.md", file)
            for n in r["unchecked_claims"]]


def build_shotlist(ctx, project):
    """Shot list rows from script scenes, timed by word count."""
    wpm = ctx.config.languages[project.language]["words_per_minute"]
    text = read_text(script_path(ctx, project))
    rows, start = [], 0.0
    for s in parse_scenes(text):
        dur = word_count(spoken_text(s["narration"])) / wpm * 60
        rows.append({"scene": s["number"], "start_sec": round(start), "end_sec": round(start + dur),
                     "narration_summary": s["title"], "visual_type": "", "visual_description": "",
                     "source": "", "license": "", "file": "", "status": "todo"})
        start += dur
    return rows


# ------------------------------------------------------------ scaffold

SCENE_HEADING = re.compile(r"^##\s*\[SCENE\s+\d+\]")
EMPTY_VISUAL = re.compile(r"^<!--\s*Visual:\s*-->$")


def _scene_block(text):
    """(start, end) of the scene section: from the first '## [SCENE n]' line to
    the next other '## ' heading (e.g. '## Stage checklist') or the end."""
    lines = text.splitlines(keepends=True)
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)
    first = next((i for i, l in enumerate(lines) if SCENE_HEADING.match(l.strip())), None)
    if first is None:
        return None
    end = next((i for i in range(first + 1, len(lines))
                if re.match(r"^##\s", lines[i]) and not SCENE_HEADING.match(lines[i].strip())), len(lines))
    return offsets[first], (offsets[end] if end < len(lines) else len(text))


def scene_block_unedited(text):
    """True when the scene section holds only [SCENE] headings, empty
    '<!-- Visual: -->' notes and blank lines, as in the template."""
    block = _scene_block(text)
    if block is None:
        return False
    return all(not line.strip() or SCENE_HEADING.match(line.strip()) or EMPTY_VISUAL.match(line.strip())
               for line in text[block[0]:block[1]].splitlines())


def scaffold(ctx, project):
    """Replace the template's scenes with one [SCENE] per outline point of
    plan.md. Everything outside the scene section stays byte-for-byte the same.
    Refused once anything has been written in the scenes."""
    from factory.modules import planning  # planning is a separate module; imported on use
    path = script_path(ctx, project)
    plan_file = planning.plan_path(ctx, project)
    if not plan_file.exists():
        raise FactoryError(f"plan.md is missing: {display_path(plan_file, ctx.paths.root)}")
    points = planning.parse_plan(read_text(plan_file))["outline"]
    if not points:
        raise FactoryError("plan.md has no outline points (## Outline: 1. ..., 2. ...). "
                           f"Check it with: python -m factory plan check {project.id}")
    if not path.exists():
        raise FactoryError(f"script.md is missing: {display_path(path, ctx.paths.root)}")
    text = read_text(path)
    if not scene_block_unedited(text):
        raise FactoryError("script.md already has written scenes (narration or visual notes), so scaffold "
                           "won't change it. Scaffold only fills the unedited template. To keep a copy first: "
                           f"python -m factory script snapshot {project.id}")
    newline = "\r\n" if "\r\n" in text else "\n"
    start, end = _scene_block(text)
    scenes = "".join(f"## [SCENE {i}] {point}{newline}<!-- Visual: -->{newline}{newline}{newline}"
                     for i, point in enumerate(points, 1))
    write_text_exact(path, text[:start] + scenes + text[end:])
    return points


# ------------------------------------------------------------ versions

VERSION_FILE = re.compile(r"^v(\d+)\.md$")


def versions_dir(ctx, project):
    return project.stage_dir(ctx, "script") / "versions"


def list_versions(ctx, project):
    """[(number, path)] sorted by number."""
    folder = versions_dir(ctx, project)
    if not folder.is_dir():
        return []
    found = [(int(m.group(1)), f) for f in folder.iterdir() if f.is_file() and (m := VERSION_FILE.match(f.name))]
    return sorted(found)


def snapshot(ctx, project, note=""):
    """Copy script.md to versions/vN.md (N = latest + 1). Refused when the
    script is unchanged since the latest version. Existing versions are never
    overwritten. project.json records script_version and each version's note."""
    path = script_path(ctx, project)
    if not path.exists():
        raise FactoryError(f"script.md is missing: {display_path(path, ctx.paths.root)}")
    data = path.read_bytes()
    existing = list_versions(ctx, project)
    if existing and existing[-1][1].read_bytes() == data:
        raise FactoryError(f"script.md is unchanged since v{existing[-1][0]}; no new version saved")
    number = existing[-1][0] + 1 if existing else 1
    folder = versions_dir(ctx, project)
    folder.mkdir(exist_ok=True)
    target = folder / f"v{number}.md"
    with open(target, "xb") as f:  # "x": never overwrite an existing version
        f.write(data)
    project.meta["script_version"] = number
    project.meta.setdefault("script_versions", []).append({"version": number, "date": today(),
                                                           "note": (note or "").strip()})
    project.save()
    return number, target


def _version_text(ctx, project, name):
    """Text of 'vN' / 'N' or 'current' (the working script.md)."""
    value = (name or "").strip().lower()
    if value == "current":
        return "script.md", read_text(script_path(ctx, project))
    m = re.match(r"^v?(\d+)$", value)
    versions = dict(list_versions(ctx, project))
    if not m or int(m.group(1)) not in versions:
        known = ", ".join(f"v{n}" for n in versions) or "none yet (use: script snapshot)"
        raise FactoryError(f"Unknown version '{name}'. Versions: {known}; or 'current'")
    number = int(m.group(1))
    return f"v{number}.md", read_text(versions[number])


def diff(ctx, project, a, b):
    """Unified diff lines between two versions ('vN' or 'current')."""
    name_a, text_a = _version_text(ctx, project, a)
    name_b, text_b = _version_text(ctx, project, b)
    return list(difflib.unified_diff(text_a.splitlines(), text_b.splitlines(),
                                     fromfile=name_a, tofile=name_b, lineterm=""))


# ------------------------------------------------------------ commands

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
    if r["timing"]:
        print(f"Timing at {r['words_per_minute']} words per minute ({ctx.config.languages[p.language]['name']}):")
        for t in r["timing"]:
            print(f"  [SCENE {t['number']}] {t['start']:>5.1f}–{t['end']:>5.1f} s  {t['words']:>4} words  {t['title']}")
    # M4 rules (hook, sentences, call to action, disclosure, sensitive terms);
    # length and empty scenes are already reported above.
    extra = [f for f in check_script(ctx, p) if f.code not in ("SCRIPT_NO_SCENES", "SCRIPT_EMPTY_SCENE",
                                                               "SCRIPT_LENGTH", "SCRIPT_TARGET")]
    for f in extra:
        print(f"  {format_finding(f)}")
    problems = (not r["in_range"]) or r["empty_scenes"] or r["unchecked_claims"] or failures(extra)
    return 1 if problems else 0


def cmd_text(args, ctx):
    print(project_narration(ctx, find_project(ctx, args.project)))
    return 0


def cmd_shotlist(args, ctx):
    p = find_project(ctx, args.project)
    path = p.stage_dir(ctx, "visuals") / "shotlist.csv"
    header, existing = read_csv_table(path)  # a missing file is simply recreated
    if len(existing) > 1 and not args.force:
        raise FactoryError("shotlist.csv already has rows. Use --force to overwrite.")
    rows = build_shotlist(ctx, p)
    write_csv(path, rows, csv_columns(ctx.paths, "shotlist.csv", header, p.meta["brand"], p.language))
    print(f"Wrote {len(rows)} scenes to {display_path(path, ctx.paths.root)}")
    return 0


def cmd_scaffold(args, ctx):
    p = find_project(ctx, args.project)
    points = scaffold(ctx, p)
    print(f"{p.id}: script.md now has {len(points)} scenes, one per outline point:")
    for i, point in enumerate(points, 1):
        print(f"  [SCENE {i}] {point}")
    return 0


def cmd_snapshot(args, ctx):
    p = find_project(ctx, args.project)
    number, path = snapshot(ctx, p, args.note)
    print(f"Saved v{number}: {display_path(path, ctx.paths.root)}")
    return 0


def cmd_versions(args, ctx):
    p = find_project(ctx, args.project)
    versions = list_versions(ctx, p)
    if not versions:
        print(f"No saved versions. Save one with: python -m factory script snapshot {p.id} --note \"...\"")
        return 0
    notes = {v.get("version"): v for v in p.meta.get("script_versions", []) if isinstance(v, dict)}
    wpm = ctx.config.languages[p.language]["words_per_minute"]
    print(f"{'VERSION':<8} {'DATE':<11} {'WORDS':>5} {'EST.':>6}  NOTE")
    for number, path in versions:
        words = sum(word_count(spoken_text(s["narration"])) for s in parse_scenes(read_text(path)))
        info = notes.get(number, {})
        print(f"v{number:<7} {info.get('date', '-'):<11} {words:>5} {round(words / wpm * 60):>4} s  "
              f"{info.get('note', '')}")
    current = script_path(ctx, p)
    if current.exists():
        same = versions[-1][1].read_bytes() == current.read_bytes()
        print(f"script.md is {'the same as' if same else 'changed since'} v{versions[-1][0]}.")
    return 0


def cmd_diff(args, ctx):
    p = find_project(ctx, args.project)
    lines = diff(ctx, p, args.a, args.b)
    print("\n".join(lines) if lines else f"No differences between {args.a} and {args.b}.")
    return 0


def register(sub):
    p = sub.add_parser("script", help="Script Writing Engine: scaffold, versions, timing and checks")
    s = p.add_subparsers(metavar="action", required=True)
    c = s.add_parser("check", help="length, per-scene timing, script rules and fact-check coverage")
    c.add_argument("project")
    c.set_defaults(func=cmd_check)
    t = s.add_parser("text", help="print the narration only (for recording or reading aloud)")
    t.add_argument("project")
    t.set_defaults(func=cmd_text)
    sl = s.add_parser("shotlist", help="create shot list rows from script scenes")
    sl.add_argument("project")
    sl.add_argument("--force", action="store_true")
    sl.set_defaults(func=cmd_shotlist)
    sc = s.add_parser("scaffold", help="one [SCENE] per plan.md outline point (unedited template only)")
    sc.add_argument("project")
    sc.set_defaults(func=cmd_scaffold)
    sn = s.add_parser("snapshot", help="save the current script as versions/vN.md")
    sn.add_argument("project")
    sn.add_argument("--note", default="", help="what changed in this version")
    sn.set_defaults(func=cmd_snapshot)
    vs = s.add_parser("versions", help="list saved script versions")
    vs.add_argument("project")
    vs.set_defaults(func=cmd_versions)
    df = s.add_parser("diff", help="compare two versions (vN, or 'current' for script.md)")
    df.add_argument("project")
    df.add_argument("a", help="e.g. v1")
    df.add_argument("b", help="e.g. v2 or current")
    df.set_defaults(func=cmd_diff)
