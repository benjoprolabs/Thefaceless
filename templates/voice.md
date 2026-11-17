# Voice-over: {{title}}

- **Project:** {{project_id}}
- **Language:** {{language_name}}
- **Voice preset:** {{voice_preset}}
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
python -m factory voice tts {{project_id}} --preset {{voice_preset}}
python -m factory voice import {{project_id}} my_take.wav
python -m factory voice convert {{project_id}} A001 --preset {{voice_preset}}
python -m factory voice list {{project_id}}
python -m factory voice select {{project_id}} A00X
python -m factory voice export {{project_id}} A00X --format wav
```

## Stage checklist
- [ ] Narration matches the fact-checked script
- [ ] Names and numbers pronounced correctly
- [ ] Final take selected (`voice select`)
- [ ] Final take exported to `exports/`
