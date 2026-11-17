# Phase 2 Development Plan: Content Production Engine

| | |
|---|---|
| **Status** | Approved plan. Implementation not started |
| **Baseline** | Phase 1, v0.3.4 (`main` at `b021dd8`) |
| **Target** | v0.5.0, Phase 2 complete |
| **Roadmap** | Phase 2 of 6 (see [ARCHITECTURE.md](ARCHITECTURE.md#8-roadmap-official-approved)) |

---

## 0. Ground rules

| Rule | Meaning |
|---|---|
| **Local-first** | Runs fully offline. No step needs an internet connection. |
| **Free-first** | No paid APIs, services or subscriptions. Python standard library preferred; no new packages unless approved. |
| **Excluded** | Voice Studio, audio recording, voice changer, voice cloning, TTS, ElevenLabs, paid AI APIs. The *Voice-over* stage stays a manual checklist (narration produced outside the system). Voice Studio code must not be restored. |
| **No rebuilding** | Phase 1 features are extended, not replaced. Existing commands keep working. |
| **Backward compatible** | Phase 1 projects keep working without changes. Upgrades only add files and never overwrite, rename or delete user content. |
| **Human-editable** | Markdown and CSV stay the editing surface. Users never have to edit JSON by hand. |
| **Git history** | `main` history is left unchanged; no history rewriting. |
| **Approval** | One pull request per milestone, Squash and Merge, merged only after approval. |

**Scope:**

| Area | Values |
|---|---|
| Languages | English (`en`), Bahasa Melayu (`ms`) |
| Formats | Short-form 15–90 s · Long-form 5–20 min |
| Divisions | What If & Science · Psychology · History & Mystery · Product & Affiliate · Technology & AI · Food & Cooking · Gaming |

---

## 1. Phase 1 assessment

### 1.1 What exists (reuse)

| Area | Implemented in Phase 1 |
|---|---|
| **Core** (`factory/core/`) | `Paths`/`Config`/`Context`; settings files checked when loaded; tolerant reading (Excel CSV, Windows encodings); friendly file errors; validation of platform, URL, date and number; project IDs `<date>_<lang>_<slug>` (accents simplified, Jawi fingerprint); detection of damaged, misplaced and duplicate projects |
| **Workflow** | 10 stages `01_research` … `10_analytics`; checklist gates; `--force` recorded in history; templates per stage with brand/language overrides |
| **Ideas** | `ideas.csv` per language; `ideas list/add/unlink`; score formula; idea ↔ project link |
| **Script** | `[SCENE n]` parsing; narration extraction (`script text`); word count → duration vs format limits; `[F#]` claim coverage against `factcheck.md` |
| **Shot list** | `script shotlist` generates rows from scenes, timed by word count (overwrites only with `--force`) |
| **Publishing** | `publish record/list`; validated platform URLs; `publications[]` in `project.json` |
| **Analytics** | `performance.csv` snapshots (manual); report totals by project, division and language |
| **Supporting** | Dashboard, niches, visual-style library, asset register with licence check |
| **Quality** | 126 tests (Python 3.11–3.13, root and non-root) |

### 1.2 Gaps addressed by Phase 2

| Module | Gap |
|---|---|
| Idea Management | No show/edit/re-score/tag; no rejected or archived status; no duplicate detection |
| Research Engine | Sources only in a free-text Markdown table; claims can't be traced to verified sources |
| Content Planning | `plan.md` not read or checked; no calendar; outline not connected to the script |
| Script Writing | No scaffold from the outline; no versions; no hook, sentence, CTA or division checks |
| Fact-Checking | Verdicts not enforced (❌ can advance); no link to sources; rows written by hand |
| Shot List | Regeneration wipes edits; no coverage, licence, `todo` or shot-length checks; no asset link |
| Editing Workflow | Checklist only; no edit plan or export |
| Subtitles | Not implemented |
| Quality Control | Checklist only; no automated report |
| Publishing & Analytics | Publish text not checked against platform limits; no schedule; manual analytics only, no derived metrics or import |
| Cross-cutting | Gates only check ticked boxes; no going back a stage; `project.json` has no format version; no CI |

---

## 2. Architecture

```
factory/
├── core/
│   ├── checks.py       NEW  Finding(level, code, message, file); per-stage check registry
│   ├── migrate.py      NEW  project format versions; preview by default, --apply to write; add-only
│   └── (existing: config, errors, files, options, projects, templates, validation)
└── modules/
    ├── ideas.py        Idea Management            (extended)
    ├── research.py     Research Engine            (new)
    ├── planning.py     Content Planning           (new)
    ├── scripts.py      Script Writing Engine      (extended)
    ├── factcheck.py    Fact-Checking System       (new)
    ├── shots.py        Shot List Generator        (new; `script shotlist` kept as alias)
    ├── editing.py      Editing Workflow           (new)
    ├── subtitles.py    Subtitle Management        (new)
    ├── qc.py           Quality Control System     (new)
    ├── publishing.py   Publishing                 (extended)
    ├── analytics.py    Analytics                  (extended)
    └── (unchanged: dashboard, niches, library, assets, production)
```

**Principles:**
1. **Module contract (unchanged from Phase 1):** logic functions that return data, `cmd_*` functions that print, and `register(subparsers)`. Phase 3's web UI reuses the logic functions.
2. **Checks framework:** every module registers check functions that return findings with level **FAIL**, **WARN** or **INFO**. The same checks power the stage gates, `check P`, `qc run` and `qc all`.
3. **Stronger gates:** a stage completes only when its checklist is ticked **and** it has no FAIL findings. `--force` still overrides and is recorded in history.
4. **Configurable rules:** every threshold lives in `config/rules.json`.
5. **Standard library only:** `csv`, `json`, `re`, `difflib`, `datetime`, `unicodedata`, `urllib.parse`.
6. **Dashboard unchanged** in Phase 2. UI work belongs to Phase 3.

---

## 3. Module specifications

### M1 Idea Management (`ideas.py`, extended)
- **Statuses:** `backlog → shortlisted → in_production → published`, plus `rejected` and `archived`. Only allowed transitions are accepted; `published` requires a recorded publication.
- **Data:** `ideas.csv` gains `tags`, `notes` and `updated`. Old files are read with these as empty; extra user columns are kept.
- **Functions:** show; edit (title, division, format, scores, tags, notes; score recalculated); set status; filter by status or tag; duplicate check per language (normalised title similarity, `difflib`); idea set to `published` automatically when its project records its first publication.
- **Out of scope:** online trend research, AI idea generation.

### M2 Research Engine (`research.py`, new)
- **`research.md`** stays the place for detailed research notes (narrative, findings, competition check).
- **`01_research/sources.csv`** (new) tracks sources in a structured way:

| Column | Content | Rule |
|---|---|---|
| `id` | `S1`, `S2`, … | unique, assigned automatically |
| `title` | Source title | required |
| `url` | Link | full `http(s)` URL; empty allowed for offline sources (books, interviews) |
| `publisher` | Organisation or author | optional |
| `type` | `primary` · `official` · `study` · `secondary` · `news` · `book` · `other` | from list |
| `published` | Publication date, `YYYY-MM-DD` | optional; not in the future |
| `accessed` | Date accessed, `YYYY-MM-DD` | required; not in the future |
| `verification_status` | `unverified` · `verified` · `disputed` · `outdated` | required; default `unverified` |
| `reliability` | 1–5 | optional |
| `notes` | Free text | optional |

- **Functions:** add or list sources; set verification status; check sources; copy sources from another project (no duplicates).
- **Rules:** see §7. Technology & AI sources older than the configured age are flagged.
- **Out of scope:** fetching or archiving web pages.

### M3 Content Planning (`planning.py`, new)
- **Data:** `plan.md` keeps its headings; Angle/Hook, the numbered Outline, the SEO keywords and the target date are read from it. `project.json` gains `planned_publish`.
- **Functions:** check the plan (hook, at least 3 outline points, primary keyword, valid date); check the outline against the format length; set the planned date; calendar across projects (filter by language, division and date range) with clash warnings (more than N videos per channel per day).

### M4 Script Writing Engine (`scripts.py`, extended)
- **Kept:** `[SCENE n]` structure, `[F#]` claim markers, `script check`, `script text`.
- **New:**
  - `script scaffold` builds one `[SCENE]` per outline point; allowed only while the script is still the unedited template;
  - versions: `script snapshot`, `script versions`, `script diff` (`03_script/versions/vN.md`, `difflib`);
  - per-scene timing using the language's speaking rate (English 150 wpm, Malay 140 wpm);
  - checks: hook length, sentence length, empty scenes, call to action in the last scene, division rules (Psychology medical terms; Product & Affiliate spoken disclosure).
- **Out of scope:** AI writing.

### M5 Fact-Checking System (`factcheck.py`, new)
- **Data:** `factcheck.md` table `Ref | Claim | Source(s) | Verdict | Fix`. Sources are cited by ID (`S1, S3`) from `sources.csv`. Verdicts are `✅ / ⚠️ / ❌` (also accepted: `ok / soft / remove`).
- **Functions:**
  - `factcheck sync` adds a row for each new `[F#]` claim with the claim's sentence pre-filled; it only adds rows and never changes edited rows;
  - `factcheck check` enforces the rules in §7: every claim has a row, a verdict and at least one existing source; ❌ claims must not remain in the script; ⚠️ claims need a fix; claims supported only by `unverified`, `disputed` or `outdated` sources are flagged;
  - `factcheck report` gives a summary.

### M6 Shot List Generator (`shots.py`, new)
- **Data:** `shotlist.csv` gains `asset_id`, linking rows to the asset register.
- **Functions:**
  - `shots generate` **merges** instead of overwriting: filled-in rows kept, new scenes added, timings refreshed, removed scenes flagged rather than deleted;
  - `shots link P SCENE --asset ID`;
  - `shots check`: scene coverage, time gaps and overlaps, rows not `done` when leaving Visuals, licence required for external sources (taken from the asset register when linked), short-form shots longer than the limit, linked files missing locally (warning, since media isn't in git).

### M7 Editing Workflow (`editing.py`, new)
- **Data:** `07_edit/edit_plan.csv` with `order, scene, start, end, source, transition, on_screen_text, music, notes`, generated from the shot list.
- **Functions:** generate (merging like the shot list); check (scene order and coverage, total length vs script estimate, format resolution and aspect ratio recorded, music licensed); export as CSV or as an FFmpeg concat text file. The export is text only; nothing is rendered.
- **Out of scope:** rendering or assembling video (a possible optional, free Phase 4 item).

### M8 Subtitle Management (`subtitles.py`, new)
- **Location:** `07_edit/subtitles/<project-id>.<lang>.srt` (and `.vtt`). Subtitles belong to the Edit stage, so the 10-stage structure and folder numbering are unchanged.
- **Functions:**
  - `subs generate` builds captions from the script narration and per-scene timing (or the edit plan if present), within the line-length, line-count, duration and reading-speed limits;
  - `subs import` brings in an SRT or VTT file made elsewhere and checks it;
  - `subs check` reports every problem with its caption number;
  - `subs shift` moves all times by N seconds;
  - `subs convert` converts between SRT and VTT;
  - `subs translate-template --to ms|en` copies the timings into an empty file for manual translation. No machine translation.
- **Out of scope:** speech recognition (Whisper is a possible optional, free Phase 4 item).

### M9 Quality Control System (`qc.py`, new)
- **Data:** `08_qc/qc_report.md` (generated: findings grouped by module, plus a summary); `project.json` gains `qc: {last_run, fails, warns}`. `qc.md` stays the manual checklist.
- **Functions:** `qc run P`, `qc report P`, `qc all`.
- **Gate:** the QC stage completes only when the latest report has 0 FAIL, is newer than the project's files, and `qc.md` is ticked.

### M10 Publishing & Analytics (`publishing.py`, `analytics.py`, extended)
- **Publishing:**
  - the chosen title, description and tags are read from `publish.md`;
  - `publish check` validates them against per-platform limits in `config/platforms.json`, plus the affiliate disclosure (Product & Affiliate), a sources section (What If & Science, History & Mystery) and the AI-disclosure checkbox;
  - `publish schedule` and `publish calendar`;
  - recording a publication sets the idea to `published`.
- **Analytics:**
  - `analytics import` reads platform CSV exports (e.g. YouTube Studio) using column mappings in `config/analytics_import.json`, offline;
  - derived metrics: engagement rate, % of video watched, views per day;
  - `analytics summary --by division|language|format|platform|month`;
  - `analytics export`;
  - consistency checks on snapshot dates.
  - Charts are deferred to Phases 3 and 5.

---

## 4. Data structures and file layout

```
config/
├── rules.json             NEW  all thresholds (script, research, fact check, shots, edit, subtitles, QC)
├── analytics_import.json  NEW  column mappings for platform CSV exports
├── platforms.json         + per-platform limits (title, description, tags, hashtags)
├── divisions.json         + disclosure_required, sensitive_terms, source_max_age_days
└── languages.json         + subtitle_max_cps

brands/<brand>/<lang>/ideas.csv            + tags, notes, updated
brands/<brand>/<lang>/<division>/<project-id>/
├── project.json           + schema_version: 2, planned_publish, qc{}, script_version
├── 01_research/   research.md, sources.csv (NEW)
├── 02_planning/   plan.md
├── 03_script/     script.md, versions/ (NEW)
├── 04_factcheck/  factcheck.md
├── 05_voice/      voice.md          (manual checklist; no voice tools)
├── 06_visuals/    visuals.md, shotlist.csv (+ asset_id)
├── 07_edit/       edit.md, edit_plan.csv (NEW), subtitles/ (NEW)
├── 08_qc/         qc.md, qc_report.md (NEW, generated)
├── 09_publish/    publish.md
└── 10_analytics/  performance.csv

templates/         + sources.csv, edit_plan.csv, Malay versions of new Markdown templates
.github/workflows/tests.yml   NEW (M0): free GitHub Actions test run
```

**Compatibility and migration:**
- A missing `schema_version` means version 1 (Phase 1).
- `migrate` previews by default; `migrate --apply` adds missing files from templates and sets `schema_version: 2`.
- It never edits, overwrites, renames or deletes existing content, and running it twice is safe.
- Phase 1 projects can be read and listed without migrating. New Phase 2 checks report missing Phase 2 files as findings telling the user to run `migrate`.
- New CSV files use the existing tolerant reader and writer, so Excel-saved files work.

---

## 5. Command design

Existing commands are unchanged. New commands:

| Group | Commands |
|---|---|
| Workflow | `check P` · `back P` · `migrate [--apply]` |
| Ideas | `ideas show ID` · `ideas edit ID [--title] [--division] [--format] [--demand] [--competition] [--effort] [--tags] [--notes]` · `ideas status ID STATUS` · `ideas dupes [--lang]` · `ideas list [--status] [--tag]` |
| Research | `research sources P` · `research add-source P --title --url --type --accessed [--published] [--publisher] [--reliability] [--notes]` · `research verify P S1 STATUS` · `research check P` · `research copy-sources P --from Q` |
| Planning | `plan check P` · `plan set-date P YYYY-MM-DD` · `plan calendar [--lang] [--division] [--from] [--to]` |
| Script | `script scaffold P` · `script snapshot P [--note]` · `script versions P` · `script diff P vA vB` |
| Fact check | `factcheck sync P` · `factcheck check P` · `factcheck report P` |
| Shots | `shots generate P` · `shots link P SCENE --asset ID` · `shots check P` |
| Edit | `edit plan P` · `edit check P` · `edit export P --format csv\|ffconcat` |
| Subtitles | `subs generate P [--format srt\|vtt]` · `subs import P FILE` · `subs check P [FILE]` · `subs shift P SECONDS` · `subs convert P --to srt\|vtt` · `subs translate-template P --to en\|ms` |
| QC | `qc run P` · `qc report P` · `qc all [--lang] [--division]` |
| Publishing | `publish check P` · `publish schedule P --platform X --date YYYY-MM-DD` · `publish calendar [--from] [--to]` |
| Analytics | `analytics import P --platform X FILE` · `analytics summary --by division\|language\|format\|platform\|month` · `analytics export FILE` |

`P` is a project ID or any unique part of it. `--brand`, `--lang` and `--division` are validated everywhere. Errors use Phase 1 style: a clear message, exit code 1, no tracebacks.

---

## 6. Workflow and module dependencies

```
Ideas ─▶ Research (research.md + sources.csv) ─▶ Planning (outline, date) ─▶ Script ([SCENE], [F#])
                                                                                  │
                 Fact check (claims ↔ verified sources) ◀────────────────────────┘
                         │
  Voice-over (manual) ─▶ Shot list (scenes ↔ assets) ─▶ Edit plan ─▶ Subtitles
                                                                        │
                        QC (all checks + checklist) ◀──────────────────┘
                                  │
                        Publishing (limits, schedule) ─▶ Analytics (import, summary) ─▶ Ideas (published)
```

**Stage gates** (checklist ticked **and** no FAIL findings from the listed modules):

| Stage | FAIL findings checked |
|---|---|
| 01 Research | Research |
| 02 Planning | Planning |
| 03 Script | Script |
| 04 Fact Check | Fact-Checking |
| 05 Voice-over | checklist only |
| 06 Visuals | Shot List |
| 07 Edit | Editing Workflow + Subtitles |
| 08 QC | QC report (fresh, 0 FAIL) |
| 09 Publishing | Publishing |
| 10 Analytics | none (final stage) |

---

## 7. Validation and quality-control rules

Defaults live in `config/rules.json` and can be changed there. **FAIL** blocks the stage gate; **WARN** is reported only.

| Area | Rule | Level |
|---|---|---|
| Research | `accessed` missing; date in the future; `type`, `verification_status` or `reliability` outside allowed values | FAIL |
| Research | Duplicate URL; no sources at all when leaving Research | WARN / FAIL |
| Research | Technology & AI source accessed more than 90 days ago | WARN |
| Planning | Missing hook, fewer than 3 outline points, no primary keyword, invalid date | FAIL |
| Planning | More than N videos planned per channel per day | WARN |
| Script | Estimated length outside the format limits | FAIL |
| Script | Estimated length more than 20% from the target | WARN |
| Script | Hook longer than 5 s (short-form) / 20 s (long-form) | WARN |
| Script | Empty scene | FAIL |
| Script | Sentence over 25 words; no call to action in the last scene | WARN |
| Script | Product & Affiliate script without a disclosure line | FAIL |
| Script | Psychology sensitive terms (e.g. "cure", "diagnose") | WARN |
| Fact check | Claim without a row, a verdict or a source; unknown source ID | FAIL |
| Fact check | ❌ claim still in the script; ⚠️ claim without a fix | FAIL |
| Fact check | Claim supported only by `unverified`, `disputed` or `outdated` sources | FAIL |
| Fact check | Claim supported only by sources with reliability ≤ 2 | WARN |
| Shot list | Scene without a row; row not `done` when leaving Visuals; external source without a licence | FAIL |
| Shot list | Time gap or overlap; short-form shot longer than 5 s; linked file not found locally | WARN |
| Edit plan | Missing or out-of-order scenes | FAIL |
| Edit plan | Total length more than 10% from the script estimate; unlicensed music | WARN / FAIL |
| Subtitles | Overlapping or backwards times; empty caption; broken numbering | FAIL |
| Subtitles | More than 42 characters per line; more than 2 lines; caption shorter than 0.8 s or longer than 7 s; reading speed above 17 characters/second | WARN (FAIL above 1.5× the limit) |
| QC | Report missing, older than the project files, or containing any FAIL | FAIL |
| Publishing | Title, description, tags or hashtags over the platform limit; Product & Affiliate disclosure missing | FAIL |
| Publishing | Title longer than the recommended length; no sources section (What If & Science, History & Mystery) | WARN |
| Analytics | Snapshot dated before the publication; inconsistent `days_since_publish` | WARN |

Platform limits change over time. The defaults in `config/platforms.json` carry a note to verify them against each platform's current rules.

---

## 8. Testing strategy

| Layer | Approach |
|---|---|
| Regression | All 126 Phase 1 tests must keep passing |
| Unit | Every reader (Markdown sections, fact-check table, `sources.csv`, SRT/VTT) and every rule in §7, with passing and failing examples |
| Merge safety | Shot list and edit plan regeneration never lose filled-in fields; `factcheck sync` never changes edited rows |
| Subtitles | Reference input/output files; randomised scripts (fixed seed) never produce overlaps or broken limits; SRT ↔ VTT round trip |
| Migration | On copies of the Phase 1 sample projects: preview changes nothing; `--apply` only adds files (checksums of existing files unchanged); running twice is safe |
| End to end | English, Malay and Jawi-titled projects through all 10 stages using only commands; each gate also blocks on a deliberate FAIL |
| Data protection | Excel-saved versions of every new CSV; Windows-encoded Markdown; damaged files give warnings, not crashes |
| Environment | Root and non-root runs; speed check (500 projects listed in under 3 s) |

### Continuous integration: free GitHub Actions (added in M0)
- **Workflow:** `.github/workflows/tests.yml` runs `python -m unittest discover -s tests -v` on every push and pull request.
- **Python versions:** 3.9, 3.10, 3.11, 3.12 and 3.13 on `ubuntu-latest`. This is the first time 3.9 and 3.10 run, since they couldn't be tested before. 3.14 is added as an informational job that doesn't block merging.
- **Operating systems:** `windows-latest` and `macos-latest` with one Python version each, so Windows behaviour is tested for the first time.
- **Free use:** standard GitHub-hosted runners only, no paid services and no secrets. Actions minutes are free for public repositories. Private repositories get a monthly free allowance, and Windows/macOS runners use it faster, so the Windows/macOS jobs can be limited to pull requests if needed.
- **Reporting:** any Python version or OS the hosted runners can't provide (for example an end-of-life Python version that's no longer available) is reported in the milestone PR as **not tested**, not hidden.
- **Local runs** stay the same, and the tool itself never needs the internet.

---

## 9. Milestones

One pull request per milestone, **Squash and Merge**, merged only after approval. Each PR includes tests, updated docs, a version bump and its CI results.

| Milestone | Version | Content | Depends on |
|---|---|---|---|
| **M0** Foundations | **v0.4.0** | Checks framework, `check`, `back`, `config/rules.json`, `schema_version` + `migrate`, gates using checks, **GitHub Actions CI** | – |
| **M1** Idea Management | **v0.4.1** | Statuses, show/edit/status, duplicate check, tags | M0 |
| **M2** Research Engine | **v0.4.2** | `sources.csv`, add/list/verify/check/copy | M0 |
| **M3** Content Planning | **v0.4.3** | Plan reading and checks, `planned_publish`, calendar | M0 |
| **M4** Script Writing Engine | **v0.4.4** | Scaffold, versions and diff, per-scene timing, script checks | M3 |
| **M5** Fact-Checking System | **v0.4.5** | Sync, verdict enforcement, source links and verification status | M2, M4 |
| **M6** Shot List Generator | **v0.4.6** | Merging generator, asset links, shot checks | M4 |
| **M7** Editing Workflow | **v0.4.7** | `edit_plan.csv`, checks, exports | M6 |
| **M8** Subtitle Management | **v0.4.8** | Generate, import, check, shift, convert, translation template | M4 (uses M7 timing if present) |
| **M9** Quality Control System | **v0.4.9** | `qc run/report/all`, QC gate | M1–M8 |
| **M10** Publishing & Analytics | **v0.4.10** | Publish checks, schedule and calendar, analytics import, summary and export | M1, M9 |
| **M11** Integration and release | **v0.5.0** | Full end-to-end tests, sample projects migrated (English + Malay), Malay templates, docs, final Phase 2 audit | All |

---

## 10. Acceptance criteria

| Module | Done when |
|---|---|
| **M0 Foundations** | Checks run per stage; `advance` blocks on any FAIL; `--force` overrides and is recorded; `back` works and is recorded; `migrate` preview changes nothing and `--apply` only adds files (checksum test) and is safe to repeat; CI runs on every push and PR with results reported per Python version and OS; all 126 Phase 1 tests pass |
| **M1 Idea Management** | Status changes follow the allowed transitions; show/edit/status work in English and Malay; duplicate check finds near-identical titles; old `ideas.csv` files still read; extra user columns kept |
| **M2 Research Engine** | `research.md` stays in place; `sources.csv` holds title, URL, publication date, access date, verification status and notes, with validated values; every Research rule in §7 has passing and failing tests; copying sources creates no duplicates |
| **M3 Content Planning** | `plan check` reports each missing section; calendar lists all planned dates, filters by language and division, and flags clashes |
| **M4 Script Writing Engine** | Scaffold creates one `[SCENE]` per outline point and refuses to overwrite a written script; snapshots and diff work; every Script rule in §7 tested; Malay timing uses the Malay rate |
| **M5 Fact-Checking System** | `sync` adds missing rows only (edited rows unchanged); ❌ claims left in the script, ⚠️ claims without a fix and claims backed only by unverified, disputed or outdated sources all block the stage |
| **M6 Shot List Generator** | Regenerating keeps every filled-in field (tested); coverage, licence and `done` rules enforced at the Visuals gate; asset links checked against the register |
| **M7 Editing Workflow** | Edit plan generated from the shot list and merged safely; length check against the estimate; CSV and FFmpeg concat exports are valid text |
| **M8 Subtitle Management** | Generated subtitles pass every subtitle rule for English and Malay test scripts; broken imported files report each problem with its caption number; round trip, shift and translation template work |
| **M9 Quality Control System** | `qc run` collects all module findings into `qc_report.md`; a stale report or any FAIL blocks the QC stage; `qc all` summarises every project |
| **M10 Publishing & Analytics** | Platform limits enforced from config; schedule and calendar work; a sample YouTube Studio CSV imports with correct mapping; derived metrics tested; recording a publication sets the idea to `published` |
| **Phase 2 overall** | English, Malay and Jawi projects complete all 10 stages using only commands; no paid APIs, internet access or new packages; no voice, audio or TTS code; CI green on all available environments, with untestable ones reported; docs updated; final Phase 2 audit passed |

---

## 11. Approved decisions

| # | Decision |
|---|---|
| 1 | **Structured research:** keep `research.md` for detailed notes; add `sources.csv` for structured source tracking (title, URL, publication date, access date, verification status, notes, plus type, publisher and reliability). |
| 2 | **Subtitles** live in `07_edit/subtitles/`. The pipeline stays at 10 stages with the existing folder numbering. |
| 3 | **Voice-over stage** stays as a manual checklist with no tools. |
| 4 | **Stronger gates:** FAIL findings block `advance`; `--force` overrides and is recorded. |
| 5 | **Milestones:** one PR per milestone, Squash and Merge, clear version numbers (v0.4.0 … v0.5.0), no merge without approval. |
| 6 | **Git history:** `main` history is left unchanged and not rewritten. Voice Studio code is not restored. |
| 7 | **CI:** free GitHub Actions; supported Python versions tested; untestable environments reported. No paid CI. |

---

## 12. Out of scope for Phase 2

| Item | Where it belongs |
|---|---|
| Web dashboard and UI: **three themes (Dark Brown, Black, White)** and **UI sound effects** (short interface sounds, with an on/off setting) | Phase 3: Web Dashboard & UI/UX |
| Video rendering/assembly, speech recognition for subtitles (optional, free, local tools only) | Phase 4: Content Automation |
| Charts, trend analysis, recommendations | Phase 5: Intelligence & Analytics |
| Deployment, multi-user, business features | Phase 6: Deployment & Business System |
| Voice Studio, audio recording, voice changer, voice cloning, TTS, ElevenLabs, paid AI APIs | **Excluded from all phases** |
