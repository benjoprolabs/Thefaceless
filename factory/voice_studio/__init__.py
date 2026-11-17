"""Module 10: QHAZE Voice Studio.

Layers (each replaceable, none depends on the CLI):

    cli.py       command-line front end (a future web UI calls service.py instead)
    service.py   workflows: import/record/trim/select/tts/convert/export, upload confirmation
    clones.py    personal voice cloning with consent + verification
    audio_log.py per-project audio history (05_voice/audio_log.json)
    audio.py     local audio utilities (WAV via stdlib, other formats via optional FFmpeg)
    engines/     voice engines behind one interface (mock, elevenlabs, ...)
"""
