# Voice-over: Why octopuses have three hearts

- **Project:** 2026-11-17_why-octopuses-have-three-hearts
- **Language:** English
- **Voice preset:** female-documentary
- **Method:** tts (A001 selected). A003→A004→A005 show the record → trim → voice-changer path.

Audio files live in this folder and every action is logged in `audio_log.json`:

| Folder | Contents |
|--------|----------|
| `raw/` | Original recordings and uploads. **Never modified.** |
| `edited/` | Trimmed copies of raw takes |
| `tts/` | Text-to-speech output |
| `converted/` | Voice-changer output |
| `exports/` | Final MP3/WAV for the editor |

Useful commands:
```
python -m factory voice tts 2026-11-17_why-octopuses-have-three-hearts --preset female-documentary
python -m factory voice import 2026-11-17_why-octopuses-have-three-hearts my_take.wav
python -m factory voice convert 2026-11-17_why-octopuses-have-three-hearts A001 --preset female-documentary
python -m factory voice list 2026-11-17_why-octopuses-have-three-hearts
python -m factory voice select 2026-11-17_why-octopuses-have-three-hearts A00X
python -m factory voice export 2026-11-17_why-octopuses-have-three-hearts A00X --format wav
```

## Stage checklist
- [x] Narration matches the fact-checked script
- [x] Names and numbers pronounced correctly
- [x] Final take selected (`voice select`)
- [x] Final take exported to `exports/`
