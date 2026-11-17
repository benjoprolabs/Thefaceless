# QHAZE Faceless Content Factory: Architecture

**Version:** 0.4.5 · **Phase:** 2, M5 Fact-Checking System (Python CLI, local files)

---

## 1. Scope

A local, file-based production system that takes faceless videos from **idea → published → measured**
across several content divisions, in **English and Bahasa Melayu**, for one or more brands.

### Phase 1 rules
| Rule | How it is met |
|------|---------------|
| Python CLI only | `python -m factory ...`. Standard library only, nothing to install. |
| Modular | 9 modules, each a separate Python file that registers its own commands |
| No database | Plain JSON / CSV / Markdown files |
| No authentication / web app | Not built. Module functions are UI-independent so a web UI can reuse them later |
| No paid services or API calls | None used. The only dependency is Python's standard library |
| Local files + reusable templates | `templates/` with brand/language overrides |
| Multi-brand / multi-channel ready | `brands/<brand>/brand.json` lists channels; every path is brand-scoped |
| English and Malay kept separate | `brands/<brand>/en/...` and `brands/<brand>/ms/...` with separate backlogs |

---

## 2. Content strategy (configuration)

| Concept | Values | Config file |
|---------|--------|-------------|
| Divisions | What If & Science · Psychology · History & Mystery · Product & Affiliate · Technology & AI · Food & Cooking · Gaming | `config/divisions.json` |
| Languages | English (`en`) · Bahasa Melayu (`ms`) | `config/languages.json` |
| Formats | Short-form 15–90 s (9:16) · Long-form 5–20 min (16:9) | `config/formats.json` |
| Workflow | 10 stages (below) | `config/pipeline.json` |
| Visual styles | One per division | `config/visual_styles.json` |
| Platforms | YouTube, YouTube Shorts, TikTok, Instagram Reels, Facebook, Facebook Reels + their web domains | `config/platforms.json` |
| Defaults | default brand / language | `config/settings.json` |

Each division carries **rules** (e.g. affiliate disclosure, "label speculation") that are
inserted into the research and fact-check templates of every project in that division.

---

## 3. Core workflow (10 stages)

```
Research → Content Planning → Script Writing → Fact Checking → Voice-over →
Visual Production → Video Editing → Quality Control → Publishing → Analytics
```

| # | Stage id | Folder | Template(s) | Owning module |
|---|----------|--------|-------------|---------------|
| 1 | `research`  | `01_research`  | `research.md` | Idea Manager |
| 2 | `planning`  | `02_planning`  | `plan.md` | Production Manager |
| 3 | `script`    | `03_script`    | `script.md` (Malay version in `templates/ms/`) | Script Writing Engine |
| 4 | `factcheck` | `04_factcheck` | `factcheck.md` | Fact-Checking System |
| 5 | `voice`     | `05_voice`     | `voice.md` (manual checklist; voice-over produced outside this system) | Production Manager |
| 6 | `visuals`   | `06_visuals`   | `visuals.md`, `shotlist.csv` | Visual Library |
| 7 | `edit`      | `07_edit`      | `edit.md` | Production Manager |
| 8 | `qc`        | `08_qc`        | `qc.md` | Production Manager |
| 9 | `publish`   | `09_publish`   | `publish.md` | Publishing Manager |
| 10 | `analytics` | `10_analytics` | `performance.csv` | Analytics |

**Stage gates.** Every stage template ends with a `## Stage checklist` of `- [ ]` items.
`advance` refuses to move a project forward until every box in the current stage's
Markdown files is ticked **and** the stage's automated checks (`factory/core/checks.py`) report
no FAIL findings (since v0.4.0: script length and empty scenes at Script, plus the spoken
Product & Affiliate disclosure since v0.4.4; at Fact Checking, claims missing from the fact
check and, since v0.4.5, claims without a verdict or a known, verified source, ❌ claims left in
the script and ⚠️ claims without a fix). `check P` shows them. `--force` overrides both; the override and the
skipped finding codes are recorded in the project history and shown on the dashboard.
`back P` moves a project back one stage (recorded; files unchanged).

Subtitles are part of the Edit stage (captions checklist) and Publishing (caption upload)
in this workflow.

**Voice-over stage.** This system has no voice tooling (Voice Studio was removed in v0.3.0).
The stage is a manual checklist: narration is produced outside the system, using the text
from `script text`.

---

## 4. Repository layout

```
Thefaceless/
├── config/                      Strategy + system configuration (JSON)
├── templates/                   Default templates
│   └── ms/script.md             Malay override
├── brands/
│   └── qhaze/
│       ├── brand.json           Brand, channels (one per language), enabled divisions
│       ├── templates/           (optional) brand-specific template overrides
│       ├── en/
│       │   ├── ideas.csv        English idea backlog (EN-001...)
│       │   └── <division>/<project_id>/
│       └── ms/
│           ├── ideas.csv        Malay idea backlog (MS-001...)
│           └── <division>/<project_id>/
├── assets/                      Shared media library: music/ sfx/ broll/ images/ brand/
│   └── register.csv             Licence register
├── factory/                     Python package (see §6)
├── tests/                       unittest suite
└── docs/ARCHITECTURE.md
```

### Project folder

```
brands/qhaze/en/what-if-science/2026-11-17_why-octopuses-have-three-hearts/
├── project.json                 id, brand, language, division, format, target_seconds,
│                                stage, history[], publications[]
├── 01_research/research.md
├── 02_planning/plan.md
├── 03_script/script.md, versions/vN.md (snapshots, created by `script snapshot`)
├── 04_factcheck/factcheck.md
├── 05_voice/voice.md
├── 06_visuals/visuals.md, shotlist.csv
├── 07_edit/edit.md
├── 08_qc/qc.md
├── 09_publish/publish.md
└── 10_analytics/performance.csv
```

**Project ID:** `YYYY-MM-DD_<language>_<slug>` (since v0.3.4), unique per brand. Commands
accept any unique part of the ID (e.g. `octopus`). Projects created earlier keep their
`YYYY-MM-DD_<slug>` IDs; nothing is renamed.

- The slug is the title in lower-case ASCII; accents are transliterated (`Café crème` → `cafe-creme`).
- If the title has letters that can't be written in Latin letters (Jawi, Arabic, CJK...), a 6-character
  fingerprint of the full title is added (`sejarah-3f9a2c`) or used alone (`jawi-3f9a2c`), so different
  titles never share a slug. The full title is stored in `project.json`.
- The language in the ID keeps the same title in English and Malay apart.
- Same title + same language + same day → refused (accidental repeat). A *different* title with the same
  slug → `-2`, `-3`, ... A folder with the ID that can't be read (damaged) → refused, never overwritten.

**Template resolution** (most specific wins):
`brands/<brand>/templates/<lang>/` → `brands/<brand>/templates/` → `templates/<lang>/` → `templates/`.
A new brand or language can restyle any template without code changes.

### Adding a brand or channel
1. Create `brands/<new>/brand.json` (copy QHAZE's) and list its channels and divisions.
2. Create `brands/<new>/<lang>/ideas.csv` with the header row.
3. Use `--brand <new>` on commands (or change `default_brand` in `config/settings.json`).

---

## 5. Software modules

| # | Module | Code | CLI | Responsibility |
|---|--------|------|-----|----------------|
| 1 | Dashboard | `modules/dashboard.py` | `dashboard` | Pipeline counts, languages, divisions, backlog, items needing attention |
| 2 | Niche Manager | `modules/niches.py` | `niches`, `niches show` | Divisions, rules, visual style, project counts per language |
| 3 | Idea Manager | `modules/ideas.py` | `ideas`, `ideas add / show / edit / status / dupes / check / unlink` | Per-language backlog, scoring, status life cycle, tags and notes, duplicate detection, consistency check, idea ↔ project links (published on first publication) |
| – | Research Engine | `modules/research.py` | `research sources / add-source / verify / check / copy-sources` | Structured source list per project (`sources.csv`), Research-stage checks and gate |
| – | Content Planning | `modules/planning.py` | `plan check / set-date / calendar` | Reads and checks `plan.md`, `planned_publish`, publishing calendar with per-channel clash warnings |
| 4 | Script Writing Engine | `modules/scripts.py` | `script check / text / shotlist / scaffold / snapshot / versions / diff` | Parse scenes, word count → duration vs format limits, per-scene timing at the language's rate, Script rules (hook, sentence length, call to action, disclosure, sensitive terms), [F#] claim coverage, scaffold from the plan outline, versions in `03_script/versions/` with `difflib` diffs, shot list from scenes |
| – | Fact-Checking System | `modules/factcheck.py` | `factcheck sync / check / report` | Reads the `factcheck.md` table, adds rows for new [F#] claims (never changes edited rows), checks verdicts and cited source IDs against `sources.csv` and their verification status |
| 5 | Visual Library | `modules/library.py` | `library visuals` | Visual style per division |
| 6 | Production Manager | `modules/production.py` | `new`, `status`, `show`, `advance` | Create projects from templates, stage gates, history |
| 7 | Publishing Manager | `modules/publishing.py` | `publish`, `publish record` | Publish queue, per-platform publication records |
| 8 | Analytics | `modules/analytics.py` | `analytics add / report` | Performance snapshots; totals by project, division, language |
| 9 | Asset Manager | `modules/assets.py` | `assets add / list / check` | Shared media + licence register, missing-licence checks |

### Code structure

```
factory/
├── __main__.py          python -m factory
├── cli.py               Builds the parser from MODULES; validates --brand/--lang/--division; safe output encoding; prints errors and warnings
├── core/
│   ├── errors.py        FactoryError + plain-language descriptions of file-system errors
│   ├── config.py        Paths, Config (cached, shape-checked JSON settings), Context (+ warnings)
│   ├── files.py         Encoding-tolerant text/JSON reading, Excel-tolerant CSV, slugify, checklists
│   ├── templates.py     {{placeholder}} rendering, override lookup, standard CSV columns
│   ├── projects.py      Project model, damaged-project detection, iter_projects, find_project
│   ├── checks.py        Findings (FAIL/WARN/INFO) and per-stage check registry used by gates and `check`
│   ├── migrate.py       Project format versions; add-only upgrade steps (`migrate`)
│   ├── options.py       Shared CLI options and validation (brand, language, division, format)
│   └── validation.py    Platform, URL, date and number validation
└── modules/             Modules 1–9 (one file each)
```

**Module contract.** Each module exposes:
- plain functions that take a `Context` and return data (no printing). A future web UI calls these;
- `cmd_*` functions that print for the CLI;
- `register(subparsers)` to add its commands. `cli.MODULES` lists them.

`Context(root)` holds `paths` + `config`. Tests pass a temporary root, so they never touch real data.

---

## 6. Data files

| File | Format | Written by |
|------|--------|-----------|
| `<project>/01_research/sources.csv` | `id,title,url,publisher,type,published,accessed,verification_status,reliability,notes` (since v0.4.2; project format 3) | Research Engine |
| `brands/<b>/<lang>/ideas.csv` | `id,title,division,format,demand,competition,effort,score,status,project_id,created,tags,notes,updated` (the last three since v0.4.1; older files are read without them and gain them on the next write). Statuses: `backlog`, `shortlisted`, `in_production`, `published`, `rejected`, `archived` | Idea Manager, Production Manager, Publishing Manager |
| `project.json` | JSON | Production, Publishing |
| `10_analytics/performance.csv` | one row per snapshot; latest row per platform is used | Analytics |
| `assets/register.csv` | `id,type,file,source,license,added,notes` | Asset Manager |

**Idea score:** `(demand×2 + (6−competition) + (6−effort)) / 4` → 1.0–5.0.

### Robustness rules

| Situation | Behaviour |
|-----------|-----------|
| CSV saved by Excel: UTF-8 BOM, Windows (cp1252) encoding, `;` separators, padded headers, blank rows, short rows | Read correctly. When the tool writes the file (e.g. `ideas add`), it is rewritten as standard UTF-8 comma-separated CSV; extra user columns are kept |
| Idea list missing a required column | Clear error naming the file and the expected first row |
| Non-numeric score (e.g. `#VALUE!`) or malformed idea ID | Treated as 0 / ignored for numbering; never crashes |
| Damaged `project.json` (invalid JSON, not an object, missing required fields, wrong field types, unknown stage/language/format) | Project skipped; `Warning: Skipped damaged project <path>: <reason>` printed after the command; dashboard shows a count; the folder can't be overwritten by `new` |
| `project.json` missing optional fields (`brand`, `target_seconds`, `publications`, `idea_id`, `created`) | Safe defaults in memory (brand from the folder, length from the format); written only when the project is next saved |
| Project folder copied, renamed or moved (id ≠ folder name, or language/division/brand ≠ folder path) | Skipped with a warning saying where it should be |
| Stage folder, a stage checklist file, or the checklist inside it deleted | Counted as a blocker by `advance` ("missing" / "checklist was removed"); `--force` still overrides and is recorded |
| Idea linked to a project that was deleted | `ideas` shows a ⚠ hint; `ideas unlink ID` resets status/project_id, refused while any folder with that project ID exists |
| Two folders with the same project id in a brand | **All** copies skipped with one warning listing both paths, so nothing is listed or counted twice (checked across the whole brand, even when filtering) |
| Markdown, template or JSON file saved as Windows-1252/Latin-1 or with a BOM | Read correctly (UTF-8 → Windows-1252 → Latin-1) |
| Broken `config/*.json` or `brand.json` (invalid JSON, wrong shape, missing keys) | Clear error naming the file, line/key and `git checkout -- <file>` to restore |
| `performance.csv` / `shotlist.csv` deleted, emptied or with columns removed | Standard columns come from the template; extra user columns and old rows are kept; a value is never dropped silently |
| Unknown `--lang`, `--brand` or `--division` (any command) | Error listing valid values; input is case-insensitive (`MS` → `ms`); an empty value is an error |
| `new --idea X --lang L` where L is not the idea's language | `Conflicting options` error explaining both fixes (drop `--lang`, or add the idea to the other language's backlog). A matching `--lang` is allowed. A title, `--division` or `--format` given with `--idea` replaces the idea's value |
| Permission denied / file locked (e.g. open in Excel) / missing file / disk full / read-only disk | `cli.main` turns any `OSError` into a plain message with the file path and a suggested fix; never a traceback. `new` removes a half-created project folder; if only the idea list can't be updated, the message says the project exists and how to finish the link by hand. An unreadable `project.json` is skipped with reason "permission denied" |
| Python older than 3.9 | `python -m factory` stops with "needs Python 3.9 or newer" before importing anything else |
| `publish record` | Platform must be in `config/platforms.json` (case-insensitive); URL must be a full `http(s)://` link on that platform's domain; date `YYYY-MM-DD`, not in the future; the same URL can't be recorded twice |
| `analytics add` | Platform must be known **and** already recorded as a publication of that project; all numbers ≥ 0; CTR 0–100 |

---

## 7. Testing

`python -m unittest discover -s tests -v` (292 tests, < 8 s, no network). CI: `.github/workflows/tests.yml` (free GitHub Actions).

| File | Covers |
|------|--------|
| `test_core.py` | rendering, template overrides, slugify, checklists, scoring |
| `test_repo_data.py` | committed config matches the strategy; sample project complete; no API keys in repo; Voice Studio fully removed |
| `test_modules.py` | modules 1–9: project creation, EN/MS separation, format limits, stage gates, ideas, script analysis, assets, publishing, analytics, dashboard |
| `test_cli.py` | complete 10-stage workflow through CLI commands only; command list |
| `test_audit_fixes.py` | Excel CSV handling, damaged projects, `.gitignore` media rules, `--lang` validation, platform/URL/date/number validation |
| `test_compat_errors.py` | `--idea`/`--lang` conflicts; friendly permission/file errors (simulated, plus a real read-only test that runs for non-root users); Python 3.9/3.10 grammar, newer-API scan, stdlib-only imports, version guard |
| `test_hardening.py` | file encodings, broken settings files, incomplete/mistyped `project.json`, copied/misplaced/duplicate projects, analytics and shot-list column recovery, removed leftovers |
| `test_remaining_fixes.py` | stage gates with deleted folders/files/checklists, `--brand`/`--division` validation, ID generation (accents, Jawi, suffixes, duplicates), EN/MS same-title IDs, `ideas unlink` |
| `test_m0_foundations.py` | checks framework, gates using checks, `check`, `back`, `rules.json`, format versions and `migrate` (checksum safety), path display, output encoding, CRLF files, guards for encodings, CI and excluded features |
| `test_m1_ideas.py` | idea status rules, `new --idea` from backlog/shortlisted only, EN-001 sample data, `ideas check` rules, project-side warnings, duplicates (English, Malay, Jawi), edit and locked fields, show/list filters, automatic published, old and Excel-saved files, Phase 1 regression |
| `test_m2_research.py` | `sources.csv` add/list/verify/check/copy, every Research rule, the Research gate, the three M2 decisions, format 3 and `migrate` |
| `test_m3_planning.py` | `plan.md` reading, every Planning rule, outline length, `set-date`, calendar filters and clashes, the Planning gate |
| `test_m4_scripts.py` | scaffold (one scene per outline point, refuses written scripts, CRLF), snapshots/versions/diff, per-scene timing (Malay rate), every Script rule, rules from config, the Script gate |
| `test_m5_factcheck.py` | `factcheck.md` reading (verdicts, source IDs), `sync` (adds rows only, edited rows unchanged, CRLF), every Fact check rule, report, the Fact Check gate, projects past the stage, sample unchanged |

### Python version support

Verified by free GitHub Actions CI (`.github/workflows/tests.yml`) on every pull request:

| Environment | Status |
|---|---|
| Ubuntu · Python 3.10, 3.11, 3.12, 3.13 | Full test suite passes |
| Ubuntu 24.04 · Python 3.9 | Full test suite passes (3.9 is end-of-life and has no build for the newer `ubuntu-latest` image, so it runs on 24.04) |
| Windows · Python 3.13 | Full test suite passes (default file encoding cp1252; one Unix-permission test is skipped by design) |
| macOS (arm64, `macos-latest`) · Python 3.13 | Full test suite passes |
| macOS (Intel, `macos-15-intel`) · Python 3.13 | Full test suite passes (separate runner pool, so macOS is still tested when no arm64 runner is free) |
| Ubuntu · Python 3.13 with a non-UTF-8 locale | Full test suite passes (guards against encoding regressions) |
| Ubuntu · Python 3.14 | Informational job (doesn't block merging); passes |
| Python < 3.9 | Not supported; clear message at start-up |

---

## 8. Roadmap (official, approved)

| Phase | Name | Status |
|-------|------|--------|
| 1 | Core System & Foundation | ✅ Complete (v0.3.4) |
| 2 | Content Production Engine | Not started (awaiting approval) |
| 3 | Web Dashboard & UI/UX | Not started |
| 4 | Content Automation | Not started |
| 5 | Intelligence & Analytics | Not started |
| 6 | Deployment & Business System | Not started |

### Rules for every phase
- **Free-first:** no paid APIs or paid services; free, local tools only, added as optional extras.
- **Out of scope:** Voice Studio, audio recording, TTS, voice cloning, voice changing and ElevenLabs.
- Each phase starts only after explicit approval.

### Phase 2: Content Production Engine (scope)
Builds on the Phase 1 workflow. Must include:
research and idea management · content planning · script writing · fact-checking · shot lists ·
editing workflow · **subtitle workflow** · quality control · publishing · analytics.

### Phase 3: Web Dashboard & UI/UX (recorded requirements)
- A local web dashboard built on the existing module functions (no logic duplicated in the UI).
- **Three themes:** Dark Brown, Black and White.
- **UI sound effects:** short interface sounds (e.g. clicks, confirmations), from free or own
  sound files, with an on/off setting. These are interface feedback only, not voice or audio
  production features.

### Phase 1 history
v0.1.0 foundation → v0.2.0 strategy and modules → v0.3.0 Voice Studio removed (scope reset) →
v0.3.1 audit fixes → v0.3.2 compatibility and error handling → v0.3.3 hardening →
v0.3.4 remaining audit issues.
