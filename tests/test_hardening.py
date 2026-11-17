"""Regression tests for the final-audit hardening round (v0.3.3).

B1  Stage Markdown saved in a non-UTF-8 encoding no longer crashes anything
B2  Broken settings files (config/*.json, brand.json) give a clear error
B3  project.json missing optional fields gets safe defaults; bad types are reported
B4  Copied / misplaced project folders are detected (no duplicates, no double counting)
B5  Analytics never silently drops numbers when performance.csv is missing/damaged
B11 Unused Voice Studio helpers removed
"""

import json
import shutil
import unittest

import factory.core.files as files
from factory.core.config import ROOT, FactoryError
from factory.core.files import read_csv, read_text
from factory.core.projects import find_project, iter_projects
from factory.modules import analytics, publishing, scripts
from factory.modules.production import advance, create_project, stage_blockers
from tests.helpers import add_source, make_sandbox, remove_sandbox, run_cli


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = create_project(self.ctx, "Main project", "en", "psychology", created="2026-01-01")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        return run_cli(list(argv), self.ctx)

    def no_traceback(self, out):
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Error:  ", out)


# ------------------------------------------------------------------ B1
class TestTextEncodings(Base):
    def write_research(self, data):
        (self.p.folder / "01_research/research.md").write_bytes(data)

    def test_read_text_handles_common_encodings(self):
        path = self.tmp / "t.md"
        for data, expected in ((b"caf\xc3\xa9", "café"), (b"\xef\xbb\xbfcaf\xc3\xa9", "café"),
                               (b"caf\xe9 \x93quote\x94", "café “quote”"), (b"\x81\x8d\x8f", "\x81\x8d\x8f")):
            path.write_bytes(data)
            self.assertEqual(read_text(path), expected)

    def test_windows_ansi_markdown_in_dashboard_and_advance(self):
        self.write_research(b"# Research caf\xe9 \x93Malaysia\x94\n- [ ] Sources checked\n")
        for argv in (["dashboard"], ["status"], ["show", "main-project"]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 0, f"{argv}: {out}")
            self.no_traceback(out)
        code, out = self.cli("advance", "main-project")
        self.assertEqual(code, 1)
        self.assertIn("research.md: Sources checked", out)   # gate still works
        self.write_research(b"# Research caf\xe9\n- [x] Sources checked\n")
        self.assertEqual(stage_blockers(self.ctx, self.p), [])
        add_source(self.ctx, self.p)  # M2: a source is required to leave Research
        code, out = self.cli("advance", "main-project")
        self.assertEqual(code, 0, out)

    def test_non_utf8_script_and_factcheck(self):
        (self.p.folder / "03_script/script.md").write_bytes(
            b"## [SCENE 1] Hook\nSelamat datang ke caf\xe9 kami [F1].\n")
        (self.p.folder / "04_factcheck/factcheck.md").write_bytes(b"| F1  | caf\xe9 claim | 1 | ok |\n")
        r = scripts.analyse(self.ctx, self.p)
        self.assertEqual((r["claims"], r["unchecked_claims"]), ([1], []))
        code, out = self.cli("script", "text", "main-project")
        self.assertIn("Selamat datang ke café kami.", out)

    def test_brand_template_in_windows_encoding(self):
        tpl = self.ctx.paths.brand_dir("qhaze") / "templates" / "qc.md"
        tpl.parent.mkdir(parents=True)
        tpl.write_bytes(b"# QC caf\xe9 {{title}}\n- [ ] ok\n")
        p = create_project(self.ctx, "Templated", "en", "gaming", created="2026-01-01")
        self.assertEqual((p.folder / "08_qc/qc.md").read_text(encoding="utf-8"), "# QC café Templated\n- [ ] ok\n")


# ------------------------------------------------------------------ B2
class TestBrokenSettingsFiles(Base):
    def break_file(self, rel, content):
        (self.tmp / rel).write_text(content, encoding="utf-8")

    def assert_clear_error(self, argv, *expected):
        code, out = self.cli(*argv)
        self.assertEqual(code, 1, out)
        self.no_traceback(out)
        for text in expected:
            self.assertIn(text, out)
        return out

    def test_invalid_json_in_each_config_file(self):
        for name, argv in (("settings", ["status"]), ("languages", ["ideas"]), ("formats", ["new", "X", "--lang", "en", "--division", "gaming"]),
                           ("divisions", ["niches"]), ("pipeline", ["status"]), ("platforms", ["publish", "record", "main-project", "--platform", "youtube", "--url", "https://youtu.be/a"]),
                           ("visual_styles", ["library", "visuals"])):
            original = (self.tmp / f"config/{name}.json").read_text(encoding="utf-8")
            self.break_file(f"config/{name}.json", "{\n  \"a\": 1,\n}")
            self.ctx.config._cache.clear()
            self.assert_clear_error(argv, f"config/{name}.json is not valid JSON (line ",
                                    f"git checkout -- config/{name}.json")
            (self.tmp / f"config/{name}.json").write_text(original, encoding="utf-8")
            self.ctx.config._cache.clear()

    def test_broken_brand_json(self):
        self.break_file("brands/qhaze/brand.json", "{")
        self.assert_clear_error(["dashboard"], "brands/qhaze/brand.json is not valid JSON")

    def test_wrong_shape_is_reported(self):
        cases = [
            ("config/pipeline.json", {"stage": []}, "missing 'stages'"),
            ("config/pipeline.json", {"stages": {}}, "'stages' must be a list"),
            ("config/pipeline.json", {"stages": [{"id": "research"}]}, "item 1 of 'stages' is missing 'folder'"),
            ("config/languages.json", {"en": {"name": "English"}}, "'en' is missing 'words_per_minute'"),
            ("config/divisions.json", {"gaming": "Gaming"}, "'gaming' must be an object"),
            ("config/settings.json", [], "it must contain a JSON object"),
            ("brands/qhaze/brand.json", {"id": "qhaze", "name": "Q", "divisions": [], "channels": [{"id": "x"}]},
             "item 1 of 'channels' is missing 'name'"),
        ]
        for rel, data, expected in cases:
            original = (self.tmp / rel).read_text(encoding="utf-8")
            (self.tmp / rel).write_text(json.dumps(data), encoding="utf-8")
            self.ctx.config._cache.clear()
            self.assert_clear_error(["dashboard"], f"{rel} has a problem: {expected}")
            (self.tmp / rel).write_text(original, encoding="utf-8")
        self.ctx.config._cache.clear()
        code, out = self.cli("dashboard")
        self.assertEqual(code, 0, out)

    def test_committed_config_passes_schema(self):
        from factory.core.config import Context
        ctx = Context()
        for name in ("settings", "languages", "formats", "divisions", "pipeline", "platforms", "visual_styles"):
            ctx.config._load(name)
        for brand in ctx.config.brand_ids():
            ctx.config.brand(brand)


# ------------------------------------------------------------------ B3
class TestIncompleteProjectJson(Base):
    def rewrite(self, change):
        path = self.p.folder / "project.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        change(meta)
        path.write_text(json.dumps(meta), encoding="utf-8")

    def test_missing_optional_fields_get_defaults(self):
        def drop(meta):
            for key in ("brand", "target_seconds", "publications", "idea_id", "created"):
                del meta[key]
        self.rewrite(drop)
        for argv in (["show", "main-project"], ["script", "check", "main-project"], ["status"],
                     ["publish"], ["analytics", "report"], ["dashboard"]):
            code, out = self.cli(*argv)
            self.no_traceback(out)
            self.assertNotIn("Skipped", out, argv)
        p = find_project(self.ctx, "main-project")
        self.assertEqual((p.meta["brand"], p.meta["target_seconds"], p.meta["publications"], p.meta["created"]),
                         ("qhaze", 60, [], "2026-01-01"))
        # Defaults are not written until the project is saved by a command
        self.assertNotIn("brand", json.loads((self.p.folder / "project.json").read_text(encoding="utf-8")))
        advance(self.ctx, p, force=True)
        self.assertEqual(json.loads((self.p.folder / "project.json").read_text(encoding="utf-8"))["brand"], "qhaze")

    def test_bad_types_are_reported_not_crashed(self):
        cases = [
            (lambda m: m.update(target_seconds="sixty"), "'target_seconds' must be a whole number"),
            (lambda m: m.update(target_seconds=True), "'target_seconds' must be a whole number"),
            (lambda m: m.update(publications={"youtube": "x"}), "'publications' must be a list"),
            (lambda m: m.update(publications=[{"platform": "youtube"}]), "'publications' must be a list"),
            (lambda m: m.update(history=["research"]), "'history' must be a list"),
            (lambda m: m.update(title=""), "'title' must be non-empty text"),
            (lambda m: m.update(division=7), "'division' must be non-empty text"),
        ]
        original = (self.p.folder / "project.json").read_text(encoding="utf-8")
        for change, expected in cases:
            self.rewrite(change)
            self.ctx.warnings.clear()
            code, out = self.cli("status")
            self.assertEqual(code, 0, out)
            self.no_traceback(out)
            self.assertIn(expected, out)
            (self.p.folder / "project.json").write_text(original, encoding="utf-8")


# ------------------------------------------------------------------ B4
class TestCopiedOrMisplacedProjects(Base):
    def setUp(self):
        super().setUp()
        while self.p.stage != "publish":
            advance(self.ctx, self.p, force=True)
        publishing.record_publication(self.ctx, self.p, "youtube", "https://youtu.be/a", "2026-01-02")
        analytics.add_snapshot(self.ctx, self.p, "youtube", views=1000)

    def test_copy_into_another_division_is_not_double_counted(self):
        dest = self.tmp / "brands/qhaze/en/gaming" / self.p.folder.name
        shutil.copytree(self.p.folder, dest)
        code, out = self.cli("status")
        self.assertIn("it says division 'psychology' but is stored in the 'gaming' folder", out)
        self.assertEqual(out.count("2026-01-01_en_main-project"), 2)  # once in the list, once in the warning
        self.assertEqual(analytics.report(self.ctx, "qhaze")["projects"][0]["views"], 1000)
        self.assertEqual(len(analytics.report(self.ctx, "qhaze")["projects"]), 1)

    def test_true_duplicates_are_all_skipped_with_warning(self):
        dest = self.tmp / "brands/qhaze/en/gaming" / self.p.folder.name
        shutil.copytree(self.p.folder, dest)
        meta = json.loads((dest / "project.json").read_text(encoding="utf-8"))
        meta["division"] = "gaming"
        (dest / "project.json").write_text(json.dumps(meta), encoding="utf-8")
        code, out = self.cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn("Skipped duplicate project id '2026-01-01_en_main-project' found in", out)
        self.assertIn("brands/qhaze/en/gaming/2026-01-01_en_main-project", out)
        self.assertIn("brands/qhaze/en/psychology/2026-01-01_en_main-project", out)
        self.assertEqual(analytics.report(self.ctx, "qhaze")["projects"], [])  # nothing counted twice
        self.assertEqual(list(iter_projects(self.ctx, division="psychology")), [])  # found even when filtered
        with self.assertRaises(FactoryError) as e:
            find_project(self.ctx, "main-project")
        self.assertIn("damaged or duplicated", str(e.exception))

    def test_copy_in_same_division_with_new_folder_name(self):
        shutil.copytree(self.p.folder, self.p.folder.with_name("2026-01-01_en_main-project-copy"))
        code, out = self.cli("status")
        self.assertIn("doesn't match the folder name '2026-01-01_en_main-project-copy'", out)
        self.assertEqual(len(analytics.report(self.ctx, "qhaze")["projects"]), 1)

    def test_language_mismatch_detected(self):
        dest = self.tmp / "brands/qhaze/ms/psychology" / self.p.folder.name
        dest.parent.mkdir(parents=True)
        shutil.move(str(self.p.folder), str(dest))
        for argv in (["status", "--lang", "ms"], ["status", "--lang", "en"]):
            code, out = self.cli(*argv)
            self.assertNotIn("2026-01-01_en_main-project       ", out)
            self.assertIn("it says language 'en' but is stored in the 'ms' folder", out)
            self.assertIn("move it to brands/qhaze/en/psychology/", out)

    def test_brand_mismatch_detected(self):
        meta = json.loads((self.p.folder / "project.json").read_text(encoding="utf-8"))
        meta["brand"] = "other"
        (self.p.folder / "project.json").write_text(json.dumps(meta), encoding="utf-8")
        code, out = self.cli("status")
        self.assertIn("it says brand 'other' but is stored under brands/qhaze/", out)


# ------------------------------------------------------------------ B5
class TestAnalyticsNeverDropsNumbers(Base):
    METRICS = dict(views=1500, watch_time_hours=12.5, avg_view_duration_sec=30.0, ctr_percent=4.2, likes=90,
                   comments=7, shares=3, subscribers_gained=11, days_since_publish=7, notes="n")

    def setUp(self):
        super().setUp()
        while self.p.stage != "publish":
            advance(self.ctx, self.p, force=True)
        publishing.record_publication(self.ctx, self.p, "youtube", "https://youtu.be/a", "2026-01-02")
        self.csv = analytics.perf_path(self.ctx, self.p)

    def assert_all_saved(self):
        analytics.add_snapshot(self.ctx, self.p, "youtube", **self.METRICS)
        row = read_csv(self.csv)[-1]
        for key, value in self.METRICS.items():
            self.assertEqual(row[key], str(value), key)
        self.assertEqual(analytics.report(self.ctx, "qhaze")["projects"][0]["views"], 1500)

    def test_file_deleted(self):
        self.csv.unlink()
        self.assert_all_saved()

    def test_file_emptied(self):
        self.csv.write_text("", encoding="utf-8")
        self.assert_all_saved()

    def test_columns_removed_keeps_old_rows_and_extra_columns(self):
        self.csv.write_text("date_recorded,platform,views,my_note\n2026-01-03,youtube,10,keep\n", encoding="utf-8")
        self.assert_all_saved()
        rows = read_csv(self.csv)
        self.assertEqual((rows[0]["views"], rows[0]["my_note"], rows[0]["likes"]), ("10", "keep", ""))

    def test_rows_without_platform_are_ignored_in_report(self):
        analytics.add_snapshot(self.ctx, self.p, "youtube", views=5)
        with open(self.csv, "a", encoding="utf-8") as f:
            f.write("2026-01-04,,999\n")
        self.assertEqual(analytics.report(self.ctx, "qhaze")["projects"][0]["views"], 5)

    def test_cli_logs_every_flag(self):
        self.csv.unlink()
        code, out = self.cli("analytics", "add", "main-project", "--platform", "youtube", "--views", "1500",
                             "--likes", "90", "--ctr", "4.2", "--subs", "11")
        self.assertEqual(code, 0, out)
        row = read_csv(self.csv)[-1]
        self.assertEqual((row["views"], row["likes"], row["ctr_percent"], row["subscribers_gained"]),
                         ("1500", "90", "4.2", "11"))

    def test_shotlist_rebuilt_when_missing_or_empty(self):
        (self.p.folder / "03_script/script.md").write_text("## [SCENE 1] Hook\nHello there.\n", encoding="utf-8")
        shot = self.p.folder / "06_visuals/shotlist.csv"
        for prepare in (shot.unlink, lambda: shot.write_text("", encoding="utf-8"),
                        lambda: shot.write_bytes(b"scene,narration_summary,my_col\r\n")):
            prepare()
            code, out = self.cli("script", "shotlist", "main-project", "--force")
            self.assertEqual(code, 0, out)
            rows = read_csv(shot)
            self.assertEqual((rows[0]["scene"], rows[0]["status"]), ("1", "todo"))
        self.assertIn("my_col", shot.read_text(encoding="utf-8").splitlines()[0])


# ------------------------------------------------------------------ B11
class TestVoiceLeftoversRemoved(unittest.TestCase):
    def test_unused_helpers_gone(self):
        for name in ("sha256", "make_private"):
            self.assertFalse(hasattr(files, name), name)
        source = (ROOT / "factory/core/files.py").read_text(encoding="utf-8")
        self.assertNotIn("private", source)
        self.assertNotIn("def sha256", source)  # hashlib is now used only for title fingerprints


if __name__ == "__main__":
    unittest.main()
