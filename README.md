# QHAZE Faceless Content Factory

A local, file-based system for producing faceless videos in **English and Bahasa Melayu**,
from idea to published to measured. It uses plain files plus a Python command-line tool, with
no database, no login and no paid services.

> **Status:** Phase 1 (v0.3.2). Voice Studio was removed in a scope reset; development is paused pending approval of the next phase. Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

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

Tested on Python 3.11, 3.12 and 3.13. The code is written for 3.9+ and checked automatically
against the 3.9/3.10 grammar, but it has **not yet been run on 3.9 or 3.10**. Older Pythons get a
clear "needs Python 3.9 or newer" message.

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
| 3 Idea Manager | `ideas [--lang en\|ms] [--division ...]` · `ideas add "Title" --lang ms --division gaming --format short --demand 4 --competition 2 --effort 2` |
| 4 Script Studio | `script check P` · `script text P` · `script shotlist P` |
| 5 Visual Library | `library visuals [--division ...]` |
| 6 Production Manager | `new "Title" --lang en --division psychology --format short [--seconds 60]` · `new --idea MS-002` (language comes from the idea) · `status` · `show P` · `advance P [--force]` |
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

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

78 tests, no network needed. One test needs a non-administrator account and is skipped when run as root/admin.

## Editing CSV files in Excel

Idea lists (`ideas.csv`), shot lists and the asset register can be opened and saved in Excel,
including with `;` separators or Windows encodings. Keep the first row (column names) unchanged.
The next time the tool writes the file, it is saved back as a standard CSV.

## Publishing and analytics rules

- Platforms: `youtube`, `youtube_shorts`, `tiktok`, `instagram_reels`, `facebook`, `facebook_reels`
  (see `config/platforms.json`; names are not case-sensitive).
- URLs must be full links on that platform, e.g. `https://www.tiktok.com/@qhaze/video/...`.
- Analytics can only be logged for a platform the video was recorded as published on.

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

## Media files

Video, image, audio and design files (`.mp4`, `.webm`, `.avi`, `.png`, `.jpg`, `.psd`, `.wav`, …)
are git-ignored because of their size, in upper or lower case. Keep them in the project folders on
your computer or a cloud drive. To commit one specific file (e.g. a small logo), add an exception
line such as `!assets/brand/logo.png` to `.gitignore`.
