import unittest

from factory.core.config import FactoryError
from factory.core.files import read_csv
from factory.core.projects import find_project
from factory.modules import analytics, assets, dashboard, ideas, publishing, scripts
from factory.modules.production import advance, create_project, stage_blockers
from tests.helpers import add_source, make_sandbox, remove_sandbox, tick_all, write_script


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()

    def tearDown(self):
        remove_sandbox(self.tmp)

    def new(self, title="Test video", lang="en", division="psychology", fmt="short", **kw):
        return create_project(self.ctx, title, lang, division, fmt, created="2026-01-01", **kw)


class TestProduction(Base):
    def test_create_builds_10_stage_folders_in_language_division_path(self):
        p = self.new()
        self.assertEqual(p.folder, self.tmp / "brands/qhaze/en/psychology/2026-01-01_en_test-video")
        for stage in self.ctx.config.stages:
            self.assertTrue((p.folder / stage["folder"]).is_dir(), stage["id"])
        self.assertEqual([f.name for f in (p.folder / "05_voice").iterdir()], ["voice.md"])
        self.assertNotIn("voice_preset", p.meta)
        for md in p.folder.rglob("*.md"):
            self.assertNotIn("{{", md.read_text(encoding="utf-8"), md)

    def test_malay_project_uses_malay_template_and_folder(self):
        p = self.new("Sejarah nasi lemak", lang="ms", division="food-cooking")
        self.assertIn("/ms/food-cooking/", p.folder.as_posix())
        self.assertIn("# Skrip:", (p.folder / "03_script/script.md").read_text(encoding="utf-8"))
        self.assertIn("Makanan & Masakan", (p.folder / "01_research/research.md").read_text(encoding="utf-8"))

    def test_format_and_input_validation(self):
        self.new(seconds=90)
        with self.assertRaises(FactoryError):
            self.new("Too long", seconds=91)
        with self.assertRaises(FactoryError):
            self.new("Too short long-form", fmt="long", seconds=200)
        self.new("Long ok", fmt="long", seconds=1200)
        for bad in ({"lang": "fr"}, {"division": "sports"}, {"fmt": "square"}):
            with self.assertRaises(FactoryError):
                self.new("x", **bad)
        with self.assertRaises(FactoryError):
            self.new()  # duplicate

    def test_stage_gate_and_force(self):
        p = self.new()
        self.assertTrue(stage_blockers(self.ctx, p))
        with self.assertRaises(FactoryError):
            advance(self.ctx, p)
        tick_all(p.folder / "01_research/research.md")
        add_source(self.ctx, p)  # M2: a source is required to leave Research
        self.assertEqual(advance(self.ctx, p), "planning")
        self.assertEqual(advance(self.ctx, p, force=True), "script")
        self.assertTrue(p.meta["history"][-1]["forced"])

    def test_find_project(self):
        self.new("Alpha one")
        self.new("Alpha two")
        self.assertEqual(find_project(self.ctx, "alpha-one").meta["title"], "Alpha one")
        with self.assertRaises(FactoryError):
            find_project(self.ctx, "alpha")  # ambiguous
        with self.assertRaises(FactoryError):
            find_project(self.ctx, "zzz")


class TestIdeas(Base):
    def test_add_idea_numbering_per_language(self):
        idea = ideas.add_idea(self.ctx, "qhaze", "ms", "Ujian", "gaming", "short", 5, 1, 1)
        self.assertEqual(idea["id"], "MS-005")
        self.assertEqual(idea["score"], 5.0)
        with self.assertRaises(FactoryError):
            ideas.add_idea(self.ctx, "qhaze", "en", "x", "gaming", "short", 6, 1, 1)

    def test_project_from_idea_links_backlog(self):
        lang, idea = ideas.find_idea(self.ctx, "qhaze", "en-002")
        p = self.new(idea["title"], lang=lang, division=idea["division"], fmt=idea["format"], idea_id=idea["id"])
        row = [i for i in ideas.load_ideas(self.ctx, "qhaze", "en") if i["id"] == "EN-002"][0]
        self.assertEqual((row["status"], row["project_id"]), ("in_production", p.id))


class TestScriptStudio(Base):
    def test_parse_and_analyse(self):
        p = self.new()
        write_script(self.ctx, p)
        scenes = scripts.parse_scenes((p.folder / "03_script/script.md").read_text(encoding="utf-8"))
        self.assertEqual([s["number"] for s in scenes], [1, 2])
        self.assertNotIn("Visual", scenes[0]["narration"])
        self.assertEqual(scripts.spoken_text(scenes[0]["narration"]), "This is a test hook sentence.")
        r = scripts.analyse(self.ctx, p)
        self.assertEqual(r["claims"], [1])
        self.assertEqual(r["unchecked_claims"], [1])
        self.assertFalse(r["in_range"])  # ~20 words is under 15 s
        fc = p.folder / "04_factcheck/factcheck.md"
        fc.write_text(fc.read_text(encoding="utf-8").replace("| F1  |                              |", "| F1  | test claim |"), encoding="utf-8")
        self.assertEqual(scripts.analyse(self.ctx, p)["unchecked_claims"], [])

    def test_shotlist_from_scenes(self):
        p = self.new()
        write_script(self.ctx, p)
        rows = scripts.build_shotlist(self.ctx, p)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["start_sec"], 0)
        self.assertEqual(rows[1]["start_sec"], rows[0]["end_sec"])


class TestAssetsPublishingAnalytics(Base):
    def test_assets_register_and_check(self):
        src = self.tmp / "song.mp3"
        src.write_bytes(b"x")
        row = assets.add_asset(self.ctx, src, "music", source="Free Music Archive", license="")
        self.assertTrue((self.tmp / "assets/music/song.mp3").exists())
        self.assertEqual(row["id"], "AS0001")
        self.assertEqual(len(assets.check_assets(self.ctx)), 1)  # missing licence
        (self.tmp / "assets/sfx").mkdir()
        (self.tmp / "assets/sfx/whoosh.wav").write_bytes(b"x")
        self.assertEqual(len(assets.check_assets(self.ctx)), 2)  # + unregistered file
        with self.assertRaises(FactoryError):
            assets.add_asset(self.ctx, src, "music")

    def test_publish_requires_stage_then_analytics_report(self):
        p = self.new()
        with self.assertRaises(FactoryError):
            publishing.record_publication(self.ctx, p, "youtube", "https://youtu.be/abc")
        while p.stage != "publish":
            advance(self.ctx, p, force=True)
        publishing.record_publication(self.ctx, p, "youtube_shorts", "https://youtube.com/shorts/x", "2026-01-05")
        publishing.record_publication(self.ctx, p, "tiktok", "https://www.tiktok.com/@q/video/1", "2026-01-05")
        with self.assertRaises(FactoryError):
            publishing.record_publication(self.ctx, p, "myspace", "https://myspace.com/x")
        analytics.add_snapshot(self.ctx, p, "youtube_shorts", views=100, likes=5)
        analytics.add_snapshot(self.ctx, p, "youtube_shorts", views=250, likes=9)  # newer snapshot wins
        analytics.add_snapshot(self.ctx, p, "tiktok", views=50)
        r = analytics.report(self.ctx, "qhaze")
        self.assertEqual(r["projects"][0]["views"], 300)
        self.assertEqual(r["divisions"]["psychology"]["views"], 300)
        self.assertEqual(len(read_csv(p.folder / "10_analytics/performance.csv")), 3)

    def test_dashboard_overview(self):
        self.new()
        self.new("Melayu", lang="ms", division="gaming")
        o = dashboard.overview(self.ctx, "qhaze")
        self.assertEqual(o["by_language"], {"en": 1, "ms": 1})
        self.assertEqual(o["by_stage"]["research"], 2)
        expected = {lang: sum(i["status"] == "backlog" for i in ideas.load_ideas(self.ctx, "qhaze", lang))
                    for lang in ("en", "ms")}
        self.assertEqual(o["backlog"], expected)


if __name__ == "__main__":
    unittest.main()
