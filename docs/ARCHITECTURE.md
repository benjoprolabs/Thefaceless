# QHAZE Faceless Content Factory: Architecture

Version: Phase 1 (foundation), v0.1.0

## 1. Goals

A local, file-based system that takes a faceless video from **idea → published → measured**.
Phase 1 deliberately has **no web interface, no database, no authentication and no paid APIs**.
Everything is plain files (Markdown, CSV, JSON) plus a small Python CLI that uses only the
standard library.

## 2. Design principles

1. **Files are the database.** Every piece of data is a human-readable file you can open,
   edit and back up without the CLI.
2. **One folder per video.** A project folder holds everything for that video, organised by stage.
3. **Configuration over code.** Channel settings and pipeline stages live in `config/`.
   Adding or renaming a stage is a JSON edit, not a code change.
4. **Small, single-purpose modules.** Each pipeline area gets its own Python module, so features
   can be added without touching unrelated code.
5. **Free and local first.** Future automation (TTS, subtitles, assembly) will use free local tools
   (Piper, Whisper, FFmpeg) before any paid service is considered.

## 3. Repository layout

```
Thefaceless/
├── config/
│   ├── channel.json        Channel name, niche, tone, formats (short/long), words-per-minute
│   └── pipeline.json       Ordered stages: id, folder, label, templates to copy
├── templates/              Reusable templates with {{placeholders}}
│   ├── idea.md             Research brief + sources + score
│   ├── script.md           Scene-based script (hook → points → CTA)
│   ├── voice.md            Voice-over checklist
│   ├── shotlist.csv        Scene-by-scene visual plan with licensing columns
│   ├── edit.md             Editing checklist
│   └── publish.md          Titles, description, tags, platforms, pre-publish checks
├── ideas/ideas.csv         Idea backlog (scored)
├── projects/<date>_<slug>/ One folder per video (see §4)
├── assets/                 Shared library: music/, sfx/, broll/, brand/
├── analytics/performance.csv  Performance log (manual entry in Phase 1)
├── factory/                Python package (the CLI)
├── tests/                  unittest test suite
└── docs/                   This document
```

## 4. Project folder (one video)

```
projects/2026-11-17_why-octopuses-have-three-hearts/
├── project.json     id, title, idea_id, format, current stage, stage history
├── 01_research/     idea.md
├── 02_script/       script.md
├── 03_voice/        voice.md (+ voiceover.wav, not committed)
├── 04_visuals/      shotlist.csv (+ clips/images)
├── 05_edit/         edit.md
├── 06_subtitles/    .srt files
└── 07_export/       publish.md (+ final.mp4, thumbnail.png)
```

The stage folders and the templates copied into them are driven by `config/pipeline.json`.

## 5. Pipeline stages → the 8 system areas

| # | Area | Stage id | Phase 1 (now) | Planned |
|---|------|----------|---------------|---------|
| 1 | Research & ideas | `research` | `ideas.csv` backlog, scoring formula, `idea.md` brief | `idea add`, idea scoring command |
| 2 | Script generation | `script` | Scene-based `script.md` with word/time target | word count + runtime check; optional local-LLM drafts |
| 3 | AI voice-over | `voice` | `voice.md` checklist | Piper TTS (local) wrapper |
| 4 | Visuals & footage | `visuals` | `shotlist.csv` with license tracking, `assets/` library | shot list generated from script scenes |
| 5 | Video editing | `edit` | `edit.md` checklist | FFmpeg rough-cut assembly |
| 6 | Subtitles | `subtitles` | folder only | script → SRT (estimated timing); Whisper (exact timing) |
| 7 | Export & publishing | `export` | `publish.md` checklist | export presets, publish log |
| 8 | Performance tracking | `published` | `analytics/performance.csv` | `track` and `report` commands |

## 6. Python package (`factory/`)

| Module | Responsibility |
|--------|----------------|
| `__main__.py` | Enables `python -m factory` |
| `cli.py` | Argument parsing; one `cmd_*` function per command |
| `config.py` | `Paths` (all file locations) + loading `channel.json` / `pipeline.json` |
| `templates.py` | Minimal `{{placeholder}}` renderer |
| `ideas.py` | Read idea backlog, scoring formula |
| `projects.py` | Create projects from templates, read/write `project.json`, list projects |

**Data flow for `python -m factory new --idea IDEA-001`:**

```
cli.cmd_new ─▶ ideas.find_idea (ideas.csv)
            └▶ projects.create_project
                 ├─ config.load_channel / load_stages
                 ├─ for each stage: mkdir + templates.render(template) → file
                 └─ write project.json (stage = first stage)
```

`Paths` takes a root folder, so tests run against a temporary copy and never touch real data.

### Idea score formula

```
score = (demand × 2 + (6 − competition) + (6 − effort)) / 4      # 1.0 – 5.0
```
Demand counts double; low competition and low effort raise the score.

## 7. How to extend

- **New command:** add `cmd_xyz(args, paths)` in `cli.py`, register it in `build_parser()`.
  Put real logic in a module (e.g. `factory/subtitles.py`), not in `cli.py`.
- **New stage or template:** add the template to `templates/` and reference it in
  `config/pipeline.json`. New projects pick it up automatically.
- **New format** (e.g. `square`): add it under `formats` in `config/channel.json`.
- **Tests:** add to `tests/`, use `make_sandbox()` for anything that writes files.

## 8. Roadmap

- **Phase 1 Step 1 (this):** structure, templates, docs, CLI (`info`, `stages`, `ideas`, `new`, `status`), sample project, tests.
- **Phase 1 Step 2:** `idea add`, `advance` (move project to next stage with checklist).
- **Phase 1 Step 3:** script word-count/runtime check, script → shot list, script → SRT.
- **Phase 1 Step 4:** `track` and `report` for performance data.
- **Phase 2 (later):** free local tools (Piper, Whisper, FFmpeg), optional simple local web UI.
- **Out of scope until decided:** database, authentication, paid API integrations.

## 9. Conventions

- Project IDs: `YYYY-MM-DD_slug-of-title`.
- Large media (`.mp4`, `.wav`, `.mp3`, …) is git-ignored. Store it locally or on a cloud drive.
- Every fact in a script must have a source in `01_research/idea.md`.
- Every external clip or track must have its source and license in `shotlist.csv`.
