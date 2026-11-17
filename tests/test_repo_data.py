"""Validates the real, committed configuration, templates and sample project."""

import re
import unittest

from factory.core.config import ROOT, Context
from factory.core.files import read_csv, unchecked_items
from factory.core.projects import iter_projects
from factory.modules.ideas import score
from factory.modules.scripts import analyse


class TestRepoData(unittest.TestCase):
    def setUp(self):
        self.ctx = Context()
        self.cfg = self.ctx.config

    def test_strategy_config(self):
        self.assertEqual(len(self.cfg.divisions), 7)
        self.assertEqual(set(self.cfg.languages), {"en", "ms"})
        self.assertEqual((self.cfg.formats["short"]["min_seconds"], self.cfg.formats["short"]["max_seconds"]), (15, 90))
        self.assertEqual((self.cfg.formats["long"]["min_seconds"], self.cfg.formats["long"]["max_seconds"]), (300, 1200))
        self.assertEqual([s["id"] for s in self.cfg.stages],
                         ["research", "planning", "script", "factcheck", "voice", "visuals",
                          "edit", "qc", "publish", "analytics"])

    def test_every_division_has_visual_style(self):
        for div in self.cfg.divisions.values():
            self.assertIn(div["visual_style"], self.cfg.visual_styles)

    def test_every_stage_template_exists(self):
        for stage in self.cfg.stages:
            for name in stage["templates"]:
                self.assertTrue((self.ctx.paths.templates / name).exists(), name)

    def test_voice_presets(self):
        presets = self.cfg.voice_presets
        for gender in ("male", "female"):
            for style in ("deep", "soft", "documentary", "storytelling"):
                p = presets[f"{gender}-{style}"]
                self.assertEqual(set(p["languages"]), {"en", "ms"})

    def test_paid_api_calls_disabled_and_no_keys_in_repo(self):
        self.assertFalse(self.cfg.voice_studio["engines"]["elevenlabs"]["calls_enabled"])
        key_like = re.compile(r"(sk_[a-f0-9]{20,}|xi-api-key\"\s*:\s*\"[a-f0-9]{20,})")
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or not path.is_file() or path.suffix not in (".py", ".json", ".md", ".csv"):
                continue
            self.assertIsNone(key_like.search(path.read_text(encoding="utf-8", errors="ignore")), path)

    def test_idea_scores_match_formula(self):
        for lang in self.cfg.languages:
            for idea in read_csv(self.ctx.paths.ideas_csv("qhaze", lang)):
                self.assertEqual(idea["id"].split("-")[0], lang.upper())
                self.assertIn(idea["division"], self.cfg.divisions)
                expected = score(int(idea["demand"]), int(idea["competition"]), int(idea["effort"]))
                self.assertEqual(float(idea["score"]), expected, idea["id"])

    def test_sample_project_complete(self):
        samples = [p for p in iter_projects(self.ctx) if p.meta.get("sample")]
        self.assertEqual(len(samples), 1)
        p = samples[0]
        self.assertEqual(p.stage, "analytics")
        self.assertEqual(len(p.meta["history"]), 10)
        self.assertTrue(p.meta["publications"])
        for md in p.folder.rglob("*.md"):
            self.assertEqual(unchecked_items(md.read_text(encoding="utf-8")), [], md)
        r = analyse(self.ctx, p)
        self.assertTrue(r["in_range"])
        self.assertEqual(r["unchecked_claims"], [])

    def test_languages_kept_separate(self):
        for p in iter_projects(self.ctx):
            self.assertEqual(p.folder.parent.parent.name, p.language)
            self.assertEqual(p.folder.parent.name, p.meta["division"])


if __name__ == "__main__":
    unittest.main()
