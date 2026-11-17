# Voice-over: Kenapa sotong kurita ada tiga jantung

- **Project:** 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung
- **Language:** Bahasa Melayu
- **Voice preset:** male-storytelling
- **Method:** <!-- tts / record + convert / record only -->

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
python -m factory voice tts 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung --preset male-storytelling
python -m factory voice import 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung my_take.wav
python -m factory voice convert 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung A001 --preset male-storytelling
python -m factory voice list 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung
python -m factory voice select 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung A00X
python -m factory voice export 2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung A00X --format wav
```

## Stage checklist
- [ ] Narration matches the fact-checked script
- [ ] Names and numbers pronounced correctly
- [ ] Final take selected (`voice select`)
- [ ] Final take exported to `exports/`
