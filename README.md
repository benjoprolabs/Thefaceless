# QHAZE Faceless Content Factory

A local, file-based system for producing faceless videos in **English and Bahasa Melayu**,
from idea to published to measured. It uses plain files plus a Python command-line tool, with
no database, no login and no paid services.

> **Status:** Phase 2 (Content Production Engine) in progress: M6 Shot List Generator (v0.4.6); M0–M5 complete. Phase 1 complete. Plan: [docs/PHASE2_PLAN.md](docs/PHASE2_PLAN.md). Free-first: no paid APIs. Roadmap and design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

| | |
|---|---|
| **Divisions** | What If & Science · Psychology · History & Mystery · Product & Affiliate · Technology & AI · Food & Cooking · Gaming |
| **Languages** | English (`en`) · Bahasa Melayu (`ms`), stored in separate folders and backlogs |
| **Formats** | Short-form 15–90 s (9:16) · Long-form 5–20 min (16:9) |
| **Workflow** | Research → Planning → Script → Fact Check → Voice-over → Visuals → Editing → QC → Publishing → Analytics |
| **Modules** | Dashboard · Niche Manager · Idea Manager · Script Studio · Visual Library · Production Manager · Publishing Manager · Analytics · Asset Manager |

---

## Setup

**Requirements:** Python 3.9+ and Git. No packages to install.

Automated tests run on free GitHub Actions for every pull request: Python 3.9–3.13 on Linux,
and Python 3.13 on Windows and macOS (see the repository's **Actions** tab). Older Pythons get a
clear "needs Python 3.9 or newer" message.

**Windows:** everything works in Command Prompt and PowerShell (`python -m factory ...`). If you
redirect output to a file and want symbols such as ✔ or Jawi text preserved, set `PYTHONUTF8=1`
first; otherwise those characters are written as `?`.

```bash
git clone https://github.com/benjoprolabs/Thefaceless.git
cd Thefaceless
python3 -m factory dashboard
```

On Windows, type `python` instead of `python3`.

---

## Voice-over

This system has no voice tools. Produce the voice-over with any tool you like, outside
this system. To get the narration text (script without headings, notes or fact-check markers):

```bash
python3 -m factory script text <project>
```

Then tick the Voice-over checklist in `05_voice/voice.md` and run `advance`.

## Quick start

```bash
python3 -m factory dashboard                 # overview
python3 -m factory ideas                     # English + Malay backlogs
python3 -m factory new --idea EN-003         # create a project from an idea
python3 -m factory status                    # all projects and their stage
python3 -m factory show spotlight            # workflow for one project (any unique part of the ID)
python3 -m factory advance spotlight         # next stage, once the stage checklist is ticked
```

Each stage's Markdown file ends with a **Stage checklist**. Tick the boxes (`- [x]`) as you work,
then run `advance`. If anything is unticked, `advance` lists what's missing.

## Command reference

| Module | Commands |
|--------|----------|
| 1 Dashboard | `dashboard` |
| 2 Niche Manager | `niches` · `niches show <division>` |
| 3 Idea Manager | `ideas [--lang en\|ms] [--division ...] [--status ...] [--tag ...]` · `ideas add "Title" --lang ms --division gaming --format short --demand 4 --competition 2 --effort 2` · `ideas show ID` · `ideas edit ID [--title] [--division] [--format] [--demand] [--competition] [--effort] [--tags] [--notes]` · `ideas status ID STATUS` · `ideas dupes [--lang]` · `ideas check [--lang]` · `ideas unlink EN-002` (after its project was deleted) |
| Research Engine | `research sources P` · `research add-source P --title "..." --type study --accessed today [--url URL] [--published] [--publisher] [--reliability 1-5] [--notes]` · `research verify P S1 verified` · `research check P` · `research copy-sources P --from Q` |
| Content Planning | `plan check P` · `plan set-date P YYYY-MM-DD` · `plan calendar [--lang] [--division] [--from] [--to]` |
| 4 Script Writing Engine | `script check P` · `script text P` · `script shotlist P` · `script scaffold P` · `script snapshot P [--note "..."]` · `script versions P` · `script diff P v1 v2` (or `v2 current`) |
| Fact-Checking System | `factcheck sync P` · `factcheck check P` · `factcheck report P` |
| Shot List Generator | `shots generate P [--force]` (same as `script shotlist`) · `shots link P SCENE --asset AS0001` · `shots check P` |
| 5 Visual Library | `library visuals [--division ...]` |
| 6 Production Manager | `new "Title" --lang en --division psychology --format short [--seconds 60]` · `new --idea MS-002` (language comes from the idea) · `status` · `show P` · `check P [--stage S] [--all]` · `advance P [--force]` · `back P` · `migrate [--apply]` |
| 7 Publishing Manager | `publish` · `publish record P --platform youtube --url https://youtu.be/...` |
| 8 Analytics | `analytics add P --platform youtube --views 1200 --likes 80 ...` · `analytics report` |
| 9 Asset Manager | `assets` · `assets add FILE --type music --source "..." --license "..."` · `assets check` |

`P` = project ID or any unique part of it. Add `--help` to any command for details.

---

## Folder overview

```
config/          Strategy + settings: divisions, languages, formats, pipeline, visual styles
templates/       Stage templates (templates/ms/ = Malay overrides)
brands/qhaze/    Brand + channels
  en/            English: ideas.csv + <division>/<project>/
  ms/            Malay:   ideas.csv + <division>/<project>/
assets/          Shared music, sfx, b-roll, images, brand kit + register.csv (licences)
factory/         Python code: core/, modules/ (1–9)
tests/           Automated tests
docs/            Architecture
```

## Sample projects

- **`brands/qhaze/en/what-if-science/2026-11-17_why-octopuses-have-three-hearts/`**: a complete
  run through all **10 stages** (research, plan, script with fact-checked claims, voice-over
  checklist, shot list, edit, QC, two publications, analytics). Its source links, URLs and
  analytics numbers are **illustrative placeholders**.
- **`brands/qhaze/ms/what-if-science/2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung/`**: a new
  Malay project at the Research stage, created from idea `MS-001` with the Malay script template.

**Sample states under M2 (intentional):** both samples were created before v0.4.2 and keep their
original files; existing `research.md` files are never modified automatically.
- The **Malay sample** is still at Research and has no `sources.csv`, so `check` correctly reports
  **FAIL** (`SOURCES_MISSING`): it can't leave Research until a source is added.
- The **English sample** is already past Research; its sources are still recorded in its
  `research.md` table rather than in `sources.csv`, so `check` correctly reports a **WARN**.

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

317 tests, no network needed. One test needs a non-administrator account and is skipped when run as root/admin.

## Research sources

Each project keeps detailed notes in `01_research/research.md` and a structured source list in
`01_research/sources.csv` (title, URL, publisher, type, publication date, access date,
verification status, reliability, notes). Links are never opened; the factory works offline.

- Add: `research add-source P --title "..." --type study --accessed today --url https://...`
  (books or interviews: leave out `--url`). Types: primary, official, study, secondary, news, book, other.
- Verify: `research verify P S1 verified` (unverified, verified, disputed, outdated).
- Check: `research check P`. A project can't leave the Research stage without at least one valid source.
  Technology & AI sources older than 90 days get a warning (`config/divisions.json`).
- Reuse: `research copy-sources P --from Q` copies another project's sources without duplicates,
  keeping their verification status and dates exactly as they were.

Projects created before v0.4.2 can get an empty `sources.csv` with `migrate --apply`; their
existing `research.md` is never changed.

## Content plans

`02_planning/plan.md` is checked when a project leaves the Planning stage: it needs a hook,
at least 3 numbered outline points, a primary keyword and a target publish date (YYYY-MM-DD).
`plan check P` shows the result. `plan set-date P 2026-12-01` stores the date in `project.json`
(`planned_publish`) and changes only the date line in `plan.md`. `plan calendar` lists planned
dates across projects and warns when one channel (language) has more than 2 videos on a day.
An outline that doesn't fit the format's length gets a warning. Limits are in `config/rules.json`.

## Scripts

- **Scaffold:** `script scaffold P` turns the plan's outline into scenes: one `## [SCENE n]` per
  outline point, titled with the point. It only works while the scenes are still the empty template;
  once any narration or visual note is written, it refuses and changes nothing.
- **Versions:** `script snapshot P --note "..."` saves `03_script/versions/vN.md` (an exact copy;
  nothing is saved if the script hasn't changed). `script versions P` lists them with their notes,
  and `script diff P v1 v2` shows the changes (`current` means the working `script.md`).
- **Timing:** `script check P` shows each scene's start and end time at the language's speaking rate
  (English 150, Malay 140 words per minute, `config/languages.json`).
- **Checks** at the Script stage: an empty scene or a length outside the format fails; a hook longer
  than 5 s (short-form) or 20 s (long-form), sentences over 25 words, and a last scene without a call
  to action get warnings. Product & Affiliate scripts must say a disclosure in the narration
  (e.g. "affiliate", "commission", "sponsored"); Psychology scripts get a warning for medical terms
  such as "cure" or "diagnose". Thresholds and phrases (English and Malay) are in `config/rules.json`
  and `config/divisions.json`. Scripts are always written by you; nothing is generated by AI.

## Fact checks

`04_factcheck/factcheck.md` has one table row per `[F#]` claim in the script:
`| F1 | claim | S1, S3 | ✅ | fix |`. Sources are cited by their ID in `01_research/sources.csv`.
Verdicts: ✅ confirmed, ⚠️ needs softer wording, ❌ remove or replace (or write `ok`, `soft`, `remove`).

- `factcheck sync P` adds a row for each claim that has none, with the claim's sentence filled in.
  It never changes a row you have edited.
- `factcheck check P` runs the checks; `factcheck report P` shows a summary of claims, verdicts and sources.
- A project can't leave the Fact Check stage while a claim has no row, verdict or source, cites an
  unknown source, is marked ❌ but is still in the script, is marked ⚠️ without a fix, or is backed
  only by unverified, disputed or outdated sources (`research verify P S1 verified`). Claims backed
  only by sources with reliability 1–2 get a warning.
- Projects already past Fact Check (such as the Phase 1 sample, whose rows cite `research.md`
  numbers) get warnings instead of failures.

## Shot lists

`06_visuals/shotlist.csv` has a row per scene: times, visual, source, licence, file, status
(`todo`, `in_progress`, `done`) and `asset_id` (a link to `assets/register.csv`).

- `shots generate P` (or `script shotlist P`) builds it from the script and **merges** on later runs:
  rows you filled in are kept, new scenes are added and times are refreshed. Rows of scenes that left
  the script get status `removed` and are never deleted; delete them yourself. A scene you split
  into several rows keeps your times. `--force` rebuilds the file from scratch.
- `shots link P 2 --asset AS0001` links scene 2 to a registered asset; it fills `file` only if empty.
- `shots check P`. A project can't leave the Visuals stage while a scene has no row, a row isn't
  `done`, an external source has no licence (a linked asset's licence from the register counts), or
  a row links an asset that isn't registered. Warnings: time gaps or overlaps, short-form shots over
  5 s, files not found locally (media isn't kept in git), removed rows. Sources that need no licence
  (`self-made`, `own`, `original`, or empty) and the 5 s limit are in `config/rules.json`.
- Projects already past Visuals (such as the sample) get warnings instead of failures.

## Idea statuses

| Status | Meaning | How it changes |
|---|---|---|
| `backlog` | New idea | `ideas status ID shortlisted / rejected / archived` |
| `shortlisted` | Chosen for production soon | back to `backlog`, or `rejected` / `archived` |
| `rejected` | Not going ahead | `backlog` or `archived` |
| `archived` | Kept for reference | `backlog` |
| `in_production` | Has a project | set automatically by `new --idea` (only from backlog or shortlisted) |
| `published` | Its project was published | set automatically by the project's first `publish record` |

Ideas with a project can't be changed by hand, so the link stays safe; once a project folder is
deleted, `ideas unlink ID` returns its idea to the backlog. Division and format are locked for
ideas with a project; title, scores, tags and notes can still be edited. `ideas dupes` finds
similar titles in the same language (threshold in `config/rules.json`), `ideas add` warns about
them, and `ideas check` reports any inconsistency without changing anything.

## Stage gates and automated checks

A stage completes (`advance`) only when its checklist is ticked **and** its automated checks have
no FAIL findings, for example an empty scene or a script outside the format's length.
`check P` lists everything for the current stage (`--stage S` for another, `--all` for every stage).
`--force` still overrides and is recorded with the findings it skipped. `back P` returns a project
to the previous stage without changing its files. Thresholds are in `config/rules.json`.

## Upgrading older projects

Projects record their file format (`schema_version`). Phase 1 projects are format 1 and keep working.
`python3 -m factory migrate` previews any upgrade; `migrate --apply` performs it. Upgrades only add
missing files and update the format number. They never overwrite or delete your content.

## Editing CSV files in Excel

Idea lists (`ideas.csv`), shot lists and the asset register can be opened and saved in Excel,
including with `;` separators or Windows encodings. Keep the first row (column names) unchanged.
The next time the tool writes the file, it is saved back as a standard CSV.

## Publishing and analytics rules

- Platforms: `youtube`, `youtube_shorts`, `tiktok`, `instagram_reels`, `facebook`, `facebook_reels`
  (see `config/platforms.json`; names are not case-sensitive).
- URLs must be full links on that platform, e.g. `https://www.tiktok.com/@qhaze/video/...`.
- Analytics can only be logged for a platform the video was recorded as published on.

## Project IDs

New projects get an ID like `2026-11-17_ms_nasi-lemak` (date, language, title). Accents are
simplified (`Café` → `cafe`). Titles in Jawi or other non-Latin scripts get a short code instead,
e.g. `2026-11-17_ms_jawi-3f9a2c`; the full title is kept in the project. The same title in English
and Malay never collides. Creating the same title twice in one language on the same day is refused.
Projects created before v0.3.4 keep their original IDs. Any unique part of an ID works in commands.

`--brand`, `--lang` and `--division` are checked by every command: a typo is an error, not an
empty list.

## If a project folder is deleted

`ideas` marks ideas whose project no longer exists. To put such an idea back in the backlog:

```bash
python3 -m factory ideas unlink EN-002
```

This is refused while the project folder still exists (even if damaged), so a working project
never loses its idea. Deleting a stage folder or checklist file does not skip a stage: `advance`
reports it as missing (or use `--force`, which is recorded).

## If a file can't be opened or saved

Errors such as "Permission denied" are shown as a short message with what to do, for example:

```
Error: Permission denied: cannot access 'brands/qhaze/en/ideas.csv'.
  - If the file is open in another program (for example Excel), close it and try again.
  - Check that your user account is allowed to read and change files in this folder.
```

Nothing is half-saved: if `new` can't write a project, the partly created folder is removed.

## If a project is damaged

If a `project.json` file can't be read, commands keep working, skip that project and print
`Warning: Skipped damaged project ...` with the reason. Fix or restore that file (e.g. with
`git checkout -- <path>`) to bring the project back.

The same warning appears if a project folder was **copied, renamed or moved**: each project's
`project.json` must match its folder (`brands/<brand>/<language>/<division>/<id>/`), and every
project id must be unique. Duplicates are skipped (all copies) so nothing is listed or counted twice.

Markdown files saved in another encoding (for example Windows Notepad "ANSI") are read correctly.
If a settings file in `config/` or a `brand.json` is broken, the error names the file and the
problem, and suggests `git checkout -- <file>` to restore it.

## Media files

Video, image, audio and design files (`.mp4`, `.webm`, `.avi`, `.png`, `.jpg`, `.psd`, `.wav`, …)
are git-ignored because of their size, in upper or lower case. Keep them in the project folders on
your computer or a cloud drive. To commit one specific file (e.g. a small logo), add an exception
line such as `!assets/brand/logo.png` to `.gitignore`.
