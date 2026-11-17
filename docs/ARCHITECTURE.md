# QHAZE Faceless Content Factory: Architecture

**Version:** 0.3.1 · **Phase:** 1 (Python CLI, local files)

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
| 3 | `script`    | `03_script`    | `script.md` (Malay version in `templates/ms/`) | Script Studio |
| 4 | `factcheck` | `04_factcheck` | `factcheck.md` | Script Studio |
| 5 | `voice`     | `05_voice`     | `voice.md` (manual checklist; voice-over produced outside this system) | Production Manager |
| 6 | `visuals`   | `06_visuals`   | `visuals.md`, `shotlist.csv` | Visual Library |
| 7 | `edit`      | `07_edit`      | `edit.md` | Production Manager |
| 8 | `qc`        | `08_qc`        | `qc.md` | Production Manager |
| 9 | `publish`   | `09_publish`   | `publish.md` | Publishing Manager |
| 10 | `analytics` | `10_analytics` | `performance.csv` | Analytics |

**Stage gates.** Every stage template ends with a `## Stage checklist` of `- [ ]` items.
`advance` refuses to move a project forward until every box in the current stage's
Markdown files is ticked. `--force` overrides it, and the override is recorded in the
project history and shown on the dashboard.

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
├── 03_script/script.md
├── 04_factcheck/factcheck.md
├── 05_voice/voice.md
├── 06_visuals/visuals.md, shotlist.csv
├── 07_edit/edit.md
├── 08_qc/qc.md
├── 09_publish/publish.md
└── 10_analytics/performance.csv
```

**Project ID:** `YYYY-MM-DD_slug`, unique per brand. Commands accept any unique part
of the ID (e.g. `octopus`).

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
| 3 | Idea Manager | `modules/ideas.py` | `ideas`, `ideas add` | Per-language backlog, scoring, links ideas to projects |
| 4 | Script Studio | `modules/scripts.py` | `script check / text / shotlist` | Parse scenes, word count → duration vs format limits, [F#] claim coverage, shot list from scenes |
| 5 | Visual Library | `modules/library.py` | `library visuals` | Visual style per division |
| 6 | Production Manager | `modules/production.py` | `new`, `status`, `show`, `advance` | Create projects from templates, stage gates, history |
| 7 | Publishing Manager | `modules/publishing.py` | `publish`, `publish record` | Publish queue, per-platform publication records |
| 8 | Analytics | `modules/analytics.py` | `analytics add / report` | Performance snapshots; totals by project, division, language |
| 9 | Asset Manager | `modules/assets.py` | `assets add / list / check` | Shared media + licence register, missing-licence checks |

### Code structure

```
factory/
├── __main__.py          python -m factory
├── cli.py               Builds the parser from MODULES; validates --lang; prints errors and warnings
├── core/
│   ├── errors.py        FactoryError (user-facing error)
│   ├── config.py        Paths (all locations), Config (cached JSON), Context (+ warnings)
│   ├── files.py         JSON helpers, Excel-tolerant CSV reading, slugify, checklist parsing
│   ├── templates.py     {{placeholder}} rendering + override lookup
│   ├── projects.py      Project model, damaged-project detection, iter_projects, find_project
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
| `brands/<b>/<lang>/ideas.csv` | `id,title,division,format,demand,competition,effort,score,status,project_id,created` | Idea Manager, Production Manager |
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
| Damaged `project.json` (invalid JSON, not an object, missing fields, unknown stage/language/format) | Project skipped; `Warning: Skipped damaged project <path>: <reason>` printed after the command; dashboard shows a count; the folder can't be overwritten by `new` |
| Unknown `--lang` (any command) | Error listing valid languages; input is case-insensitive (`MS` → `ms`) |
| `publish record` | Platform must be in `config/platforms.json` (case-insensitive); URL must be a full `http(s)://` link on that platform's domain; date `YYYY-MM-DD`, not in the future; the same URL can't be recorded twice |
| `analytics add` | Platform must be known **and** already recorded as a publication of that project; all numbers ≥ 0; CTR 0–100 |

---

## 7. Testing

`python -m unittest discover -s tests -v` (58 tests, < 1 s, no network).

| File | Covers |
|------|--------|
| `test_core.py` | rendering, template overrides, slugify, checklists, scoring |
| `test_repo_data.py` | committed config matches the strategy; sample project complete; no API keys in repo; Voice Studio fully removed |
| `test_modules.py` | modules 1–9: project creation, EN/MS separation, format limits, stage gates, ideas, script analysis, assets, publishing, analytics, dashboard |
| `test_cli.py` | complete 10-stage workflow through CLI commands only; command list |
| `test_audit_fixes.py` | Excel CSV handling, damaged projects, `.gitignore` media rules, `--lang` validation, platform/URL/date/number validation |

---

## 8. Roadmap

Development is paused after the v0.3.0 scope reset (Voice Studio removed) and the
v0.3.1 audit fixes.
The next phase will be decided and approved separately.
