"""Basic tests. Run with: python -m unittest discover -s tests -v"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from factory.cli import main
from factory.config import ROOT, Paths, load_channel, load_stages
from factory.ideas import load_ideas, score
from factory.projects import create_project, list_projects, slugify
from factory.templates import render


def make_sandbox():
    """Copy config, templates and ideas into a temp folder so tests never touch real data."""
    tmp = Path(tempfile.mkdtemp())
    for name in ("config", "templates", "ideas"):
        shutil.copytree(ROOT / name, tmp / name)
    (tmp / "projects").mkdir()
    return tmp, Paths(tmp)


def run_cli(argv, paths):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(argv, paths=paths)
    return code, out.getvalue()


class TestHelpers(unittest.TestCase):
    def test_render_replaces_known_and_keeps_unknown(self):
        self.assertEqual(render("{{a}} {{ b }} {{c}}", {"a": 1, "b": "x"}), "1 x {{c}}")

    def test_slugify(self):
        self.assertEqual(slugify("Why Octopuses Have 3 Hearts?!"), "why-octopuses-have-3-hearts")
        self.assertEqual(slugify("!!!"), "untitled")

    def test_score_range(self):
        self.assertEqual(score(5, 1, 1), 5.0)
        self.assertEqual(score(1, 5, 5), 1.0)


class TestRealRepoData(unittest.TestCase):
    """Checks that the committed config, templates and sample project are valid."""

    def setUp(self):
        self.paths = Paths()

    def test_config_loads(self):
        channel = load_channel(self.paths)
        self.assertIn(channel["default_format"], channel["formats"])
        self.assertTrue(load_stages(self.paths))

    def test_every_stage_template_exists(self):
        for stage in load_stages(self.paths):
            for name in stage["templates"]:
                self.assertTrue((self.paths.templates / name).exists(), name)

    def test_ideas_csv_scores_match_formula(self):
        for idea in load_ideas(self.paths):
            expected = score(int(idea["demand"]), int(idea["competition"]), int(idea["effort"]))
            self.assertAlmostEqual(float(idea["score"]), expected, places=1, msg=idea["id"])

    def test_sample_project_present(self):
        stage_ids = {s["id"] for s in load_stages(self.paths)}
        projects = list_projects(self.paths)
        self.assertTrue(any(p.get("sample") for p in projects))
        for p in projects:
            self.assertIn(p["stage"], stage_ids)


class TestProjects(unittest.TestCase):
    def setUp(self):
        self.tmp, self.paths = make_sandbox()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_create_project_builds_all_stage_folders(self):
        folder = create_project(self.paths, "Test Video", fmt="short", today="2026-01-01")
        self.assertEqual(folder.name, "2026-01-01_test-video")
        for stage in load_stages(self.paths):
            if stage["folder"]:
                self.assertTrue((folder / stage["folder"]).is_dir())
        script = (folder / "02_script" / "script.md").read_text()
        self.assertIn("Test Video", script)
        self.assertNotIn("{{", script)
        meta = json.loads((folder / "project.json").read_text())
        self.assertEqual(meta["stage"], "research")

    def test_duplicate_and_bad_format_rejected(self):
        create_project(self.paths, "Dup", today="2026-01-01")
        with self.assertRaises(FileExistsError):
            create_project(self.paths, "Dup", today="2026-01-01")
        with self.assertRaises(ValueError):
            create_project(self.paths, "X", fmt="vertical-ultra")


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp, self.paths = make_sandbox()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_info_stages_ideas(self):
        for cmd in ("info", "stages", "ideas"):
            code, out = run_cli([cmd], self.paths)
            self.assertEqual(code, 0, cmd)
            self.assertTrue(out.strip(), cmd)

    def test_new_from_idea_then_status(self):
        code, out = run_cli(["new", "--idea", "IDEA-002"], self.paths)
        self.assertEqual(code, 0, out)
        code, out = run_cli(["status"], self.paths)
        self.assertIn("loudest-sound", out)

    def test_new_with_unknown_idea_fails(self):
        code, out = run_cli(["new", "--idea", "IDEA-999"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("not found", out)

    def test_no_command_prints_help(self):
        code, out = run_cli([], self.paths)
        self.assertEqual(code, 0)
        self.assertIn("usage", out)


if __name__ == "__main__":
    unittest.main()
