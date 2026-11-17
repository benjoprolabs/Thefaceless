"""Personal voice cloning, with ownership consent and verification.

Lifecycle (status in voice_library/clones/<name>/voice.json):

    awaiting_consent → (sign consent.md + record phrase) → verified → (create) → ready

Rules enforced here:
- Only the owner's own voice: consent.md must have every box ticked and be
  signed with the exact owner name given at `init`.
- The owner records a random verification phrase (stored as evidence).
- consent.md is fingerprinted at verification; if it is edited afterwards,
  the clone can no longer be created or used.
- Clone data (samples, voice IDs) is git-ignored and written owner-only.
"""

import random
import shutil

from factory.core.config import FactoryError
from factory.core.files import read_json, sha256, slugify, today, unchecked_items, write_json, make_private
from factory.core.templates import render_template
from factory.voice_studio import audio

PHRASE_WORDS = ["amber", "river", "seven", "lantern", "quiet", "harbour", "violet", "thunder",
                "maple", "orbit", "copper", "meadow", "falcon", "silver", "coral", "ember"]


def clone_dir(ctx, name):
    return ctx.paths.clones / slugify(name)


def load_clone(ctx, name):
    path = clone_dir(ctx, name) / "voice.json"
    if not path.exists():
        raise FactoryError(f"No voice clone named '{name}'. Start with: voice clone init")
    return read_json(path)


def save_clone(ctx, data):
    write_json(clone_dir(ctx, data["name"]) / "voice.json", data, private=True)


def list_clones(ctx):
    if not ctx.paths.clones.exists():
        return []
    return [read_json(p) for p in sorted(ctx.paths.clones.glob("*/voice.json"))]


def init_clone(ctx, name, owner, rng=None):
    name = slugify(name)
    folder = clone_dir(ctx, name)
    if folder.exists():
        raise FactoryError(f"Clone '{name}' already exists")
    if not owner.strip():
        raise FactoryError("Owner name is required")
    rng = rng or random.SystemRandom()
    phrase = " ".join(rng.sample(PHRASE_WORDS, 5)) + f" {rng.randint(1000, 9999)}"
    for sub in ("samples", "verification"):
        (folder / sub).mkdir(parents=True)
    consent = render_template(ctx.paths, "voice/consent.md", {
        "clone_name": name, "owner": owner.strip(), "created": today(), "verification_phrase": phrase})
    (folder / "consent.md").write_text(consent, encoding="utf-8")
    data = {"name": name, "owner": owner.strip(), "status": "awaiting_consent", "created": today(),
            "verification_phrase": phrase, "samples": [], "engine_voice_ids": {}}
    save_clone(ctx, data)
    return data


def _copy_in(src, dest_dir, allowed):
    from pathlib import Path
    src = Path(src)
    if not src.is_file():
        raise FactoryError(f"File not found: {src}")
    if audio.ext(src) not in allowed:
        raise FactoryError(f"Unsupported format .{audio.ext(src)}. Use: {', '.join(allowed)}")
    dest = dest_dir / f"{len(list(dest_dir.glob('*'))) + 1:02d}_{src.name}"
    shutil.copy2(src, dest)
    make_private(dest)
    return dest


def add_sample(ctx, name, file):
    data = load_clone(ctx, name)
    dest = _copy_in(file, clone_dir(ctx, name) / "samples", ctx.config.voice_studio["import_formats"])
    data["samples"].append(dest.name)
    save_clone(ctx, data)
    return dest


def consent_problems(ctx, data):
    text = (clone_dir(ctx, data["name"]) / "consent.md").read_text(encoding="utf-8")
    problems = [f"Not ticked: {item}" for item in unchecked_items(text)]
    signed = ""
    for line in text.splitlines():
        if line.strip().lower().startswith("signed:"):
            signed = line.split(":", 1)[1].strip()
    if signed.lower() != data["owner"].lower():
        problems.append(f"Signature must be exactly the owner name: {data['owner']}")
    return problems


def verify_clone(ctx, name, recording):
    data = load_clone(ctx, name)
    problems = consent_problems(ctx, data)
    if problems:
        raise FactoryError("Consent not complete:\n  - " + "\n  - ".join(problems))
    dest = _copy_in(recording, clone_dir(ctx, name) / "verification",
                    ctx.config.voice_studio["import_formats"])
    data.update({
        "status": "verified", "verified": today(),
        "verification_recording": dest.name,
        # Phase 1 cannot transcribe audio; the phrase recording is kept as evidence
        # for manual review. A future step can check it with speech-to-text.
        "phrase_check": "manual",
        "consent_sha256": sha256(clone_dir(ctx, name) / "consent.md"),
    })
    save_clone(ctx, data)
    return data


def assert_usable(ctx, data, need_ready=True):
    """Re-check consent integrity before every use of a clone."""
    ok_status = ("ready",) if need_ready else ("verified", "ready")
    if data["status"] not in ok_status:
        raise FactoryError(f"Clone '{data['name']}' is '{data['status']}'. Complete consent and verification first.")
    if sha256(clone_dir(ctx, data["name"]) / "consent.md") != data.get("consent_sha256"):
        raise FactoryError(f"consent.md for '{data['name']}' changed after verification. Re-verify the clone.")


def create_clone(ctx, name, engine, confirm):
    data = load_clone(ctx, name)
    assert_usable(ctx, data, need_ready=False)
    samples = [clone_dir(ctx, name) / "samples" / s for s in data["samples"]]
    if not samples:
        raise FactoryError("Add at least one voice sample first: voice clone add-sample")
    if engine.sends_data_externally and not confirm(
            f"Upload {len(samples)} voice sample(s) of '{data['owner']}' to {engine.name}?"):
        raise FactoryError("Cancelled: nothing was uploaded.")
    voice_id = engine.create_clone(data["name"], samples, description=f"Personal voice of {data['owner']}")
    data["engine_voice_ids"][engine.name] = voice_id
    data["status"] = "ready"
    save_clone(ctx, data)
    return data


def delete_clone(ctx, name):
    folder = clone_dir(ctx, name)
    if not folder.exists():
        raise FactoryError(f"No voice clone named '{name}'")
    data = load_clone(ctx, name)
    shutil.rmtree(folder)
    return data
