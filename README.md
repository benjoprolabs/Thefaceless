# QHAZE Faceless Content Factory

A local, file-based system for producing faceless videos in **English and Bahasa Melayu**,
from idea to published to measured. It uses plain files plus a Python command-line tool, with
no database, no login and no paid services.

> **Status:** Phase 1 (v0.2.0). Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

| | |
|---|---|
| **Divisions** | What If & Science · Psychology · History & Mystery · Product & Affiliate · Technology & AI · Food & Cooking · Gaming |
| **Languages** | English (`en`) · Bahasa Melayu (`ms`), stored in separate folders and backlogs |
| **Formats** | Short-form 15–90 s (9:16) · Long-form 5–20 min (16:9) |
| **Workflow** | Research → Planning → Script → Fact Check → Voice-over → Visuals → Editing → QC → Publishing → Analytics |
| **Modules** | Dashboard · Niche Manager · Idea Manager · Script Studio · Voice & Visual Library · Production Manager · Publishing Manager · Analytics · Asset Manager · **Voice Studio** |

---

## Setup

**Requirements:** Python 3.9+ and Git. No packages to install.

```bash
git clone https://github.com/benjoprolabs/Thefaceless.git
cd Thefaceless
python3 -m factory dashboard
```

On Windows, type `python` instead of `python3`.

**Optional free tools** (only for some audio features):

| Tool | Needed for |
|------|-----------|
| [FFmpeg](https://ffmpeg.org) | MP3 export, trimming MP3/M4A, mic recording on macOS/Linux |
| [SoX](https://sourceforge.net/projects/sox/) | Mic recording (`rec`) on any OS |

WAV files work without either.

---

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
| 5 Voice & Visual Library | `library voices [--lang ms]` · `library visuals [--division ...]` |
| 6 Production Manager | `new "Title" --lang en --division psychology --format short [--seconds 60]` · `new --idea MS-002` · `status` · `show P` · `advance P [--force]` |
| 7 Publishing Manager | `publish` · `publish record P --platform youtube --url URL` |
| 8 Analytics | `analytics add P --platform youtube --views 1200 --likes 80 ...` · `analytics report` |
| 9 Asset Manager | `assets` · `assets add FILE --type music --source "..." --license "..."` · `assets check` |
| 10 Voice Studio | see below |

`P` = project ID or any unique part of it. Add `--help` to any command for details.

---

## Voice Studio (Module 10)

```bash
python3 -m factory voice engines                          # mock (default) and elevenlabs
python3 -m factory voice presets --lang ms                # 8 narrator presets, EN + MS

# Recorder
python3 -m factory voice record P --seconds 60            # new take from microphone
python3 -m factory voice import P my_take.m4a             # upload MP3 / WAV / M4A
python3 -m factory voice play P A001
python3 -m factory voice trim P A001 --start 0.5 --end 42 # copy into edited/, original kept

# AI voices
python3 -m factory voice tts P --voice female-documentary # script → voice-over
python3 -m factory voice convert P A002 --voice male-deep # voice changer on your recording

# Manage
python3 -m factory voice list P                           # audio history (* = selected)
python3 -m factory voice list                             # history across all projects
python3 -m factory voice select P A003                    # choose final take
python3 -m factory voice export P --format mp3            # final file in exports/
```

**Phase 1 uses the free `mock` engine.** It produces silent placeholder WAVs for TTS, and for
voice conversion it copies your recording, so you can test the whole workflow offline.

### ElevenLabs (prepared, calls disabled)

ElevenLabs is the planned production engine. In Phase 1 **no paid API calls are made**:

```bash
python3 -m factory voice tts P --engine elevenlabs --dry-run   # shows the request, sends nothing
```

When it's enabled in a later phase:
- Put your key in an **environment variable**. Never put it in a file in this repo.
  ```bash
  export ELEVENLABS_API_KEY="..."          # macOS/Linux
  setx ELEVENLABS_API_KEY "..."            # Windows
  ```
- Set each preset's `engine_voices.elevenlabs.voice_id` in `config/voice_presets.json`.
- Before anything is uploaded, you'll be asked `[y/N]`. The default is **No**.

### Personal voice cloning (your own voice only)

```bash
python3 -m factory voice clone init my-voice --owner "Your Full Name"
#   → open voice_library/clones/my-voice/consent.md, tick every box, sign with your exact name
#   → record yourself reading the verification phrase shown
python3 -m factory voice clone verify my-voice phrase.wav
python3 -m factory voice clone add-sample my-voice sample.wav    # 1–3 min of clean speech
python3 -m factory voice clone create my-voice --engine mock
python3 -m factory voice tts P --voice clone:my-voice
```

Clone data stays on your computer (git-ignored, owner-only file permissions). If `consent.md` is
edited after verification, the clone is blocked. Cloning another person's voice isn't supported.

---

## Folder overview

```
config/          Strategy + settings: divisions, languages, formats, pipeline, voices, engines
templates/       Stage templates (templates/ms/ = Malay overrides, templates/voice/ = consent form)
brands/qhaze/    Brand + channels
  en/            English: ideas.csv + <division>/<project>/
  ms/            Malay:   ideas.csv + <division>/<project>/
assets/          Shared music, sfx, b-roll, images, brand kit + register.csv (licences)
voice_library/   Personal voice clones (private, not in git)
factory/         Python code: core/, modules/ (1–9), voice_studio/ (10)
tests/           Automated tests
docs/            Architecture
```

## Sample projects

- **`brands/qhaze/en/what-if-science/2026-11-17_why-octopuses-have-three-hearts/`**: a complete
  run through all **10 stages** (research, plan, script with fact-checked claims, voice-over
  history, shot list, edit, QC, two publications, analytics). Its source links, URLs and analytics
  numbers are **illustrative placeholders**. The voice files aren't in git (audio is git-ignored),
  so `voice list` shows them as "not on this computer". Regenerate one with
  `python3 -m factory voice tts octopus`.
- **`brands/qhaze/ms/what-if-science/2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung/`**: a new
  Malay project at the Research stage, created from idea `MS-001` with the Malay script template.

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

54 tests, no network needed. MP3 tests are skipped automatically if FFmpeg isn't installed.

## Media files

Video and audio (`.mp4`, `.wav`, `.mp3`, `.m4a`, …) are git-ignored because of their size.
Keep them in the project folders on your computer or a cloud drive.
