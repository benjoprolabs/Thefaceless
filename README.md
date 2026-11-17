# QHAZE Faceless Content Factory

A simple, file-based system for producing faceless videos, from idea to published to measured.
It's built with plain files plus a small Python command-line tool, with no database, no login and no paid services.

> **Status:** Phase 1, Step 1 (foundation). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requirements

- Python **3.9+** (no extra packages needed)
- Git

Check your Python version:

```bash
python3 --version
```

## Setup

```bash
git clone https://github.com/benjoprolabs/Thefaceless.git
cd Thefaceless
python3 -m factory info
```

No `pip install` is needed. The CLI uses only Python's standard library.
(On Windows, use `python` instead of `python3`.)

## Using the CLI

Run every command from the repository folder:

| Command | What it does |
|---------|--------------|
| `python3 -m factory info` | Channel summary, number of ideas and projects |
| `python3 -m factory stages` | Lists the 8 pipeline stages |
| `python3 -m factory ideas` | Shows the idea backlog, best score first |
| `python3 -m factory new "My video title"` | Creates a new project folder from the templates |
| `python3 -m factory new --idea IDEA-002` | Creates a project from an idea in `ideas/ideas.csv` |
| `python3 -m factory new "Title" --format short` | Chooses `short` (9:16) or `long` (16:9) |
| `python3 -m factory status` | Lists all projects and their current stage |
| `python3 -m factory --help` | Help |

## Typical workflow

1. **Add an idea** as a new row in `ideas/ideas.csv` (score formula is in the architecture doc).
2. **Create the project:** `python3 -m factory new --idea IDEA-00X`
3. Work through the folders in order:
   `01_research` → `02_script` → `03_voice` → `04_visuals` → `05_edit` → `06_subtitles` → `07_export`
4. After publishing, log numbers in `analytics/performance.csv`.

For now, update a project's stage by editing `"stage"` in its `project.json`. An `advance` command comes in the next step.

## Folder overview

```
config/      Channel settings and pipeline stages (edit these to customise)
templates/   Reusable templates copied into every new project
ideas/       Idea backlog (ideas.csv)
projects/    One folder per video
assets/      Shared music, sound effects, b-roll, brand files
analytics/   Performance tracking
factory/     The Python CLI
tests/       Automated tests
docs/        Architecture and documentation
```

## Sample project

`projects/2026-11-17_why-octopuses-have-three-hearts/` is a filled-in example: an idea brief,
a scene-based script and a shot list for a ~50-second Short. Use it as a reference.
Its source URLs are placeholders, so verify the facts before publishing anything based on it.

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

## Media files

Video and audio files (`.mp4`, `.wav`, `.mp3`, …) are ignored by git because they're too large.
Keep them in the project folders on your computer or on a cloud drive.
