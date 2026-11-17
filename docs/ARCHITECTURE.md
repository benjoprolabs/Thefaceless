# QHAZE Faceless Content Factory: Architecture

**Version:** 0.2.0 · **Phase:** 1 (Python CLI, local files)

---

## 1. Scope

A local, file-based production system that takes faceless videos from **idea → published → measured**
across several content divisions, in **English and Bahasa Melayu**, for one or more brands.

### Phase 1 rules
| Rule | How it is met |
|------|---------------|
| Python CLI only | `python -m factory ...`. Standard library only, nothing to install. |
| Modular | 10 modules, each a separate Python file/package that registers its own commands |
| No database | Plain JSON / CSV / Markdown files |
| No authentication / web app | Not built. Module functions are UI-independent so a web UI can reuse them later |
| No paid API calls | ElevenLabs engine builds requests but **refuses to send** (`PaidAPIDisabled`) |
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
| Voice presets | Male/Female × Deep/Soft/Documentary/Storytelling | `config/voice_presets.json` |
| Voice engines | `mock` (default), `elevenlabs` | `config/voice_studio.json` |
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
| 5 | `voice`     | `05_voice`     | `voice.md` + `raw/ edited/ tts/ converted/ exports/` | Voice Studio |
| 6 | `visuals`   | `06_visuals`   | `visuals.md`, `shotlist.csv` | Voice & Visual Library |
| 7 | `edit`      | `07_edit`      | `edit.md` | Production Manager |
| 8 | `qc`        | `08_qc`        | `qc.md` | Production Manager |
| 9 | `publish`   | `09_publish`   | `publish.md` | Publishing Manager |
| 10 | `analytics` | `10_analytics` | `performance.csv` | Analytics |

**Stage gates.** Every stage template ends with a `## Stage checklist` of `- [ ]` items.
`advance` refuses to move a project forward until every box in the current stage's
Markdown files is ticked. `--force` overrides it, and the override is recorded in the
project history and shown on the dashboard.

Subtitles are part of the Edit stage (captions checklist) and Publishing (caption upload)
in this workflow. Automated SRT generation is a planned Script Studio / Voice Studio feature.

---

## 4. Repository layout

```
Thefaceless/
├── config/                      Strategy + system configuration (JSON)
├── templates/                   Default templates
│   ├── ms/script.md             Malay override
│   └── voice/consent.md         Voice-clone consent form
├── brands/
│   └── qhaze/
│       ├── brand.json           Brand, channels (one per language), enabled divisions, default voices
│       ├── templates/           (optional) brand-specific template overrides
│       ├── en/
│       │   ├── ideas.csv        English idea backlog (EN-001...)
│       │   └── <division>/<project_id>/
│       └── ms/
│           ├── ideas.csv        Malay idea backlog (MS-001...)
│           └── <division>/<project_id>/
├── assets/                      Shared media library: music/ sfx/ broll/ images/ brand/
│   └── register.csv             Licence register
├── voice_library/
│   └── clones/                  Personal voice clones (git-ignored, private)
├── factory/                     Python package (see §6)
├── tests/                       unittest suite
└── docs/ARCHITECTURE.md
```

### Project folder

```
brands/qhaze/en/what-if-science/2026-11-17_why-octopuses-have-three-hearts/
├── project.json                 id, brand, language, division, format, target_seconds,
│                                voice_preset, stage, history[], publications[]
├── 01_research/research.md
├── 02_planning/plan.md
├── 03_script/script.md
├── 04_factcheck/factcheck.md
├── 05_voice/
│   ├── voice.md
│   ├── audio_log.json           audio history (see §7.5)
│   ├── raw/  edited/  tts/  converted/  exports/
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
| 5 | Voice & Visual Library | `modules/library.py` | `library voices / visuals` | Narrator presets, personal clones, division visual styles |
| 6 | Production Manager | `modules/production.py` | `new`, `status`, `show`, `advance` | Create projects from templates, stage gates, history |
| 7 | Publishing Manager | `modules/publishing.py` | `publish`, `publish record` | Publish queue, per-platform publication records |
| 8 | Analytics | `modules/analytics.py` | `analytics add / report` | Performance snapshots; totals by project, division, language |
| 9 | Asset Manager | `modules/assets.py` | `assets add / list / check` | Shared media + licence register, missing-licence checks |
| 10 | **Voice Studio** | `voice_studio/` | `voice ...` | Recording, TTS, voice changer, cloning, audio management (§7) |

### Code structure

```
factory/
├── __main__.py          python -m factory
├── cli.py               Builds the parser from MODULES; prints FactoryError nicely
├── core/
│   ├── config.py        Paths (all locations), Config (cached JSON), Context, FactoryError
│   ├── files.py         JSON/CSV helpers, sha256, slugify, checklist parsing, private files
│   ├── templates.py     {{placeholder}} rendering + override lookup
│   ├── projects.py      Project model, iter_projects, find_project
│   └── options.py       Shared CLI options and validation (brand, language, division, format)
├── modules/             Modules 1–9 (one file each)
└── voice_studio/        Module 10 (package)
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
| `05_voice/audio_log.json` | JSON | Voice Studio |
| `10_analytics/performance.csv` | one row per snapshot; latest row per platform is used | Analytics |
| `assets/register.csv` | `id,type,file,source,license,added,notes` | Asset Manager |
| `voice_library/clones/<name>/voice.json` | JSON, owner-only permissions | Voice Studio |

**Idea score:** `(demand×2 + (6−competition) + (6−effort)) / 4` → 1.0–5.0.

---

## 7. Module 10: QHAZE Voice Studio

### 7.1 Layers

```
  CLI (voice_studio/cli.py)        future: web UI / API
            │                              │
            └──────────┬───────────────────┘
                       ▼
          service.py  (workflows, upload confirmation)
            │            │              │
       audio_log.py   clones.py      audio.py (WAV stdlib; FFmpeg/SoX optional)
                         │
                         ▼
          engines/  ── VoiceEngine interface
                      ├── mock.py        (default, offline, free)
                      └── elevenlabs.py  (initial production engine; calls disabled)
```

### 7.2 Features → implementation

| Feature | Phase 1 status | Command |
|---------|----------------|---------|
| **Voice Recorder** | | |
| Record from microphone | ✅ via SoX `rec`, `arecord` or FFmpeg if installed; clear message otherwise | `voice record P --seconds 60` |
| Upload MP3 / WAV / M4A | ✅ copied into `raw/` as numbered takes | `voice import P file` |
| Playback | ✅ system player (afplay/ffplay/aplay; default app on Windows) | `voice play P A001` |
| Trimming | ✅ WAV built-in; MP3/M4A with FFmpeg; result in `edited/` | `voice trim P A001 --start 1 --end 30` |
| Retakes | ✅ every import/recording = new take number; choose with `select` | `voice select P A003` |
| Keep raw originals | ✅ never modified, set read-only, SHA-256 recorded | |
| **AI Voice Changer** | | |
| Convert own recording to target voice | ✅ workflow (mock engine copies audio so pacing is preserved) | `voice convert P A001 --voice male-deep` |
| Male/female × deep/soft/documentary/storytelling | ✅ 8 presets, all EN + MS | `voice presets` |
| Preserve emotion/pacing | By design: speech-to-speech (not re-generated from text) | |
| **Text-to-Speech** | ✅ narration extracted from the script (headings, comments, [F#] removed) | `voice tts P --voice female-documentary` |
| **Personal Voice Cloning** | ✅ consent + verification workflow; mock clone creation | `voice clone init/verify/add-sample/create/list/delete` |
| **Audio Management** | ✅ audio log, history across projects, MP3/WAV export | `voice list [P]`, `voice export P --format mp3` |
| ElevenLabs API | ⏸ request builders + `--dry-run`; sending disabled | `voice tts P --engine elevenlabs --dry-run` |

### 7.3 Engine interface (replaceable)

```python
class VoiceEngine(ABC):
    name: str
    sends_data_externally: bool   # True → user must confirm before every call
    output_ext: str               # "wav", "mp3", ...
    def text_to_speech(self, text, voice_id, language, voice_settings, out_path) -> dict
    def speech_to_speech(self, in_path, voice_id, language, voice_settings, out_path) -> dict
    def create_clone(self, name, sample_paths, description="") -> str   # engine voice id
```

**Adding an engine:** write a subclass in `voice_studio/engines/`, add it to `ENGINES` in
`engines/__init__.py`, add its settings in `config/voice_studio.json`, and add its voice IDs under
each preset's `engine_voices`. Nothing else changes.

### 7.4 ElevenLabs (initial engine, disabled in Phase 1)

| Operation | Request built (not sent) | Model (config) |
|-----------|--------------------------|----------------|
| TTS | `POST /v1/text-to-speech/{voice_id}` JSON body | `eleven_multilingual_v2` (English + Malay) |
| Voice changer | `POST /v1/speech-to-speech/{voice_id}` multipart | `eleven_multilingual_sts_v2` |
| Clone | `POST /v1/voices/add` multipart (samples) | |

- The API key is read **only** from the environment variable named in config
  (`ELEVENLABS_API_KEY`) at call time. It is never written to files, logs, dry-run output or git.
  `.env` files are git-ignored.
- Every method builds the request and then raises `PaidAPIDisabled`. Missing key →
  `EngineNotConfigured`. Tests assert the module contains no networking imports.
- **To enable later (separate, explicit step):** verify endpoints/models against current
  ElevenLabs docs, implement `_send()` (HTTP + saving the response audio), set
  `"calls_enabled": true`, fill preset `voice_id`s.

### 7.5 Audio management

`05_voice/audio_log.json`:
```json
{
  "selected": "A001",
  "items": [
    {"id": "A003", "kind": "raw", "file": "raw/take-001_my_take.wav", "take": 1,
     "source_file": "my_take.wav", "duration_sec": 40.0, "sha256": "…", "created": "2026-11-17"},
    {"id": "A004", "kind": "edited", "parent": "A003", "trim": [0.5, 38.0], "…": "…"},
    {"id": "A005", "kind": "converted", "parent": "A004", "engine": "mock",
     "voice": "male-documentary", "language": "en", "…": "…"}
  ]
}
```
Kinds: `raw`, `edited`, `tts`, `converted`, `export`. `parent` links every derived file to its
source, giving a full history. `voice list` (no project) shows history across all projects.

### 7.6 Safety rules

| Requirement | Enforcement |
|-------------|-------------|
| Never upload without confirmation | `service` calls `confirm()` before any engine with `sends_data_externally`. The default answer is **No**; non-interactive input = No; `--yes` must be explicit. Cancel = nothing written. |
| Never clone another person's voice | Consent form declares *"This is my own voice"*; must be fully ticked and **signed with the exact owner name**. Only self-cloning is supported. |
| Ownership verification | Random verification phrase per clone; owner records it; recording kept as evidence (`phrase_check: manual` in Phase 1; automatic speech-to-text check planned). |
| Consent integrity | consent.md SHA-256 stored at verification; any later edit blocks creating or using the clone. |
| Store voice IDs securely | `voice_library/clones/*` is git-ignored; `voice.json` and samples are owner-only (chmod 600). No secrets stored, only engine voice IDs. |
| Keys in environment only | See §7.4. |
| Deleting | `voice clone delete` removes local data and reminds the user to delete the remote clone. |

---

## 8. Testing

`python -m unittest discover -s tests -v` (54 tests, < 2 s, no network).

| File | Covers |
|------|--------|
| `test_core.py` | rendering, template overrides, slugify, checklists, scoring |
| `test_repo_data.py` | committed config matches the strategy; sample project complete; no API keys in repo; paid calls disabled |
| `test_modules.py` | modules 1–9: project creation, EN/MS separation, format limits, stage gates, ideas, script analysis, assets, publishing, analytics, dashboard |
| `test_voice_studio.py` | recorder, raw protection, trim, TTS, convert, export, confirmation, ElevenLabs safety, full cloning consent flow |
| `test_cli.py` | complete 10-stage workflow and clone flow through CLI commands only |

---

## 9. Roadmap

| Phase | Scope |
|-------|-------|
| **1 (now)** | Everything in this document |
| 1.x | Subtitle (SRT) generation from script timing; idea/plan helpers; brand creation command |
| 2 | Enable ElevenLabs calls (after explicit approval); Whisper (local) for subtitles + verification phrase check; FFmpeg rough-cut assembly |
| 3 | Local web UI on top of the same module functions |
| Later, if needed | Database, authentication, multi-user, scheduling/uploading via platform APIs |
