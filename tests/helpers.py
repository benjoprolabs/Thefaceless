"""Test helpers: every test that writes files runs in a temporary sandbox copy."""

import io
import os
import shutil
import stat
import tempfile
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from factory.cli import main
from factory.core.config import ROOT, Context


def make_sandbox():
    """Temp root with config, templates, brand config and idea backlogs (no projects)."""
    tmp = Path(tempfile.mkdtemp(prefix="qhaze-test-"))
    shutil.copytree(ROOT / "config", tmp / "config")
    shutil.copytree(ROOT / "templates", tmp / "templates")
    for lang in ("en", "ms"):
        (tmp / "brands/qhaze" / lang).mkdir(parents=True)
        shutil.copy(ROOT / f"brands/qhaze/{lang}/ideas.csv", tmp / f"brands/qhaze/{lang}/ideas.csv")
    shutil.copy(ROOT / "brands/qhaze/brand.json", tmp / "brands/qhaze/brand.json")
    (tmp / "assets").mkdir()
    shutil.copy(ROOT / "assets/register.csv", tmp / "assets/register.csv")
    return tmp, Context(tmp)


def remove_sandbox(tmp):
    def onerror(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(tmp, onerror=onerror)


def run_cli(argv, ctx):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv, ctx=ctx)
    return code, out.getvalue() + err.getvalue()


def make_wav(path, seconds=2.0, rate=16000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))
    return path


def tick_all(path):
    path.write_text(path.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8")


SAMPLE_SCRIPT_SCENES = (
    "## [SCENE 1] Hook\n<!-- Visual: x -->\nThis is a test hook sentence [F1].\n\n"
    "## [SCENE 2] Body\nHere is the body of the video with several more words in it.\n\n"
    "## Stage checklist\n- [x] done\n"
)


def write_script(ctx, project, body=SAMPLE_SCRIPT_SCENES):
    path = project.stage_dir(ctx, "script") / "script.md"
    path.write_text("# Script\n\n" + body, encoding="utf-8")
    return path
