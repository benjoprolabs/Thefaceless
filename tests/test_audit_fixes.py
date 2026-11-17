"""Regression tests for the audit findings fixed in v0.3.1.

1. HIGH   Excel-edited idea lists (BOM, cp1252, ';' separators, blank rows, bad cells)
2. MEDIUM Damaged project.json files are skipped, not fatal
3. MEDIUM .gitignore excludes generated image/video/design files
4. LOW    Invalid --lang values give a clear error
5. LOW    Platform names, URLs, dates and numbers validated in publishing/analytics
"""

import fnmatch
import json
import shutil
import subprocess
import unittest

from factory.core.config import ROOT, FactoryError
from factory.core.files import read_csv
from factory.core.projects import find_project, iter_projects
from factory.core.validation import check_platform, check_url
from factory.modules import analytics, ideas, publishing
from factory.modules.production import advance, create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli

HEADER = "id,title,division,format,demand,competition,effort,score,status,project_id,created"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.ms_csv = self.ctx.paths.ideas_csv("qhaze", "ms")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        return run_cli(list(argv), self.ctx)


# ------------------------------------------------------------------ 1 (HIGH)
class TestExcelIdeaLists(Base):
    ROWS = ["MS-001,Kenapa sotong kurita ada tiga jantung,what-if-science,short,4,2,2,4.0,backlog,,2026-11-17",
            "MS-002,Misteri Kota Gelanggi,history-mystery,long,4,2,4,3.5,backlog,,2026-11-17"]

    def write(self, text, encoding="utf-8"):
        self.ms_csv.write_bytes(text.encode(encoding))

    def assert_lists_ok(self):
        code, out = self.cli("ideas", "--lang", "ms")
        self.assertEqual(code, 0, out)
        self.assertIn("MS-001", out)
        self.assertIn("MS-002", out)
        return out

    def test_utf8_bom(self):
        self.write("﻿" + HEADER + "\n" + "\n".join(self.ROWS) + "\n")
        self.assert_lists_ok()

    def test_semicolon_separator_and_decimal_comma(self):
        rows = [r.replace(",", ";") for r in self.ROWS]
        rows[0] = rows[0].replace(";4.0;", ';"4,0";')
        self.write(HEADER.replace(",", ";") + "\r\n" + "\r\n".join(rows) + "\r\n")
        out = self.assert_lists_ok()
        self.assertLess(out.index("MS-001"), out.index("MS-002"))  # 4,0 sorted above 3.5

    def test_windows_encoding(self):
        self.write(HEADER + "\n" + self.ROWS[0].replace("Kenapa", "Kenapa café") + "\n" + self.ROWS[1] + "\n",
                   encoding="cp1252")
        self.assertIn("café", self.assert_lists_ok())

    def test_blank_rows_padded_headers_and_short_rows(self):
        header = " , ".join(HEADER.split(","))
        self.write(header + "\n\n" + self.ROWS[0] + "\n,,,,,,,,,,\n" + self.ROWS[1].rsplit(",", 2)[0] + "\n")
        self.assert_lists_ok()

    def test_non_numeric_score_and_malformed_ids_do_not_crash(self):
        bad = self.ROWS[1].replace(",3.5,", ",#VALUE!,")
        self.write(HEADER + "\n" + self.ROWS[0] + "\n" + bad + "\nMS-x,Odd id,gaming,short,1,1,1,1,backlog,,\n")
        self.assert_lists_ok()
        idea = ideas.add_idea(self.ctx, "qhaze", "ms", "Baru", "gaming", "short", 3, 3, 3)
        self.assertEqual(idea["id"], "MS-003")

    def test_missing_column_gives_clear_error(self):
        self.write("id,title,division\nMS-001,x,gaming\n")
        code, out = self.cli("ideas", "--lang", "ms")
        self.assertEqual(code, 1)
        self.assertIn("missing column(s): format, status, project_id", out)
        self.assertNotIn("Traceback", out)

    def test_adding_to_excel_file_normalises_it(self):
        self.write("﻿" + HEADER.replace(",", ";") + "\n" + self.ROWS[0].replace(",", ";") + "\n")
        ideas.add_idea(self.ctx, "qhaze", "ms", "Baru", "gaming", "short", 3, 3, 3)
        raw = self.ms_csv.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.decode().startswith(HEADER))
        self.assertEqual([r["id"] for r in read_csv(self.ms_csv)], ["MS-001", "MS-002"])

    def test_extra_user_columns_are_kept(self):
        self.write(HEADER + ",my_notes\n" + self.ROWS[0] + ",keep me\n")
        ideas.add_idea(self.ctx, "qhaze", "ms", "Baru", "gaming", "short", 3, 3, 3)
        self.assertEqual(read_csv(self.ms_csv)[0]["my_notes"], "keep me")

    def test_create_project_from_excel_saved_idea(self):
        self.write("﻿" + HEADER.replace(",", ";") + "\n" + self.ROWS[0].replace(",", ";") + "\n")
        code, out = self.cli("new", "--idea", "MS-001")
        self.assertEqual(code, 0, out)
        self.assertEqual(read_csv(self.ms_csv)[0]["status"], "in_production")


# ---------------------------------------------------------------- 2 (MEDIUM)
class TestDamagedProjects(Base):
    def setUp(self):
        super().setUp()
        self.good = create_project(self.ctx, "Good one", "en", "psychology", created="2026-01-01")
        self.bad = create_project(self.ctx, "Bad one", "ms", "gaming", created="2026-01-01")
        self.bad_json = self.bad.folder / "project.json"

    def assert_survives(self, expected_reason):
        for argv in (["status"], ["dashboard"], ["niches"], ["publish"], ["analytics", "report"],
                     ["show", "good-one"]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 0, f"{argv}: {out}")
            self.assertIn("Warning: Skipped damaged project", out, argv)
            self.assertIn(expected_reason, out)
            self.assertNotIn("Traceback", out)
        self.assertEqual([p.id for p in iter_projects(self.ctx)], [self.good.id])

    def test_invalid_json(self):
        self.bad_json.write_text("{ broken")
        self.assert_survives("invalid JSON")

    def test_empty_file(self):
        self.bad_json.write_text("")
        self.assert_survives("invalid JSON")

    def test_not_an_object(self):
        self.bad_json.write_text("[]")
        self.assert_survives("must contain a JSON object")

    def test_missing_fields(self):
        meta = json.loads(self.bad_json.read_text())
        del meta["stage"], meta["history"]
        self.bad_json.write_text(json.dumps(meta))
        self.assert_survives("missing field(s): stage, history")

    def test_unknown_stage(self):
        meta = json.loads(self.bad_json.read_text())
        meta["stage"] = "voice-studio"
        self.bad_json.write_text(json.dumps(meta))
        self.assert_survives("unknown stage 'voice-studio'")

    def test_binary_garbage(self):
        self.bad_json.write_bytes(b"\xff\xfe\x00garbage")
        code, out = self.cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn("Skipped damaged project", out)

    def test_warning_reported_once_and_dashboard_counts_it(self):
        self.bad_json.write_text("{")
        code, out = self.cli("dashboard")
        self.assertEqual(out.count("Warning:"), 1)
        self.assertIn("Damaged projects (skipped)      : 1", out)

    def test_damaged_project_cannot_be_found_or_overwritten(self):
        self.bad_json.write_text("{")
        with self.assertRaises(FactoryError) as e:
            find_project(self.ctx, "bad-one")
        self.assertIn("damaged", str(e.exception))
        with self.assertRaises(FactoryError):  # same title/date must not overwrite the damaged folder
            create_project(self.ctx, "Bad one", "ms", "gaming", created="2026-01-01")

    def test_good_projects_still_work_end_to_end(self):
        self.bad_json.write_text("{")
        code, out = self.cli("advance", "good-one", "--force")
        self.assertEqual(code, 0, out)


# ---------------------------------------------------------------- 3 (MEDIUM)
class TestGitignore(unittest.TestCase):
    REQUIRED = ["png", "jpg", "jpeg", "webm", "avi", "psd", "gif", "webp", "mp4", "mov", "mkv",
                "wav", "mp3", "m4a"]

    def patterns(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith(("#", "!"))]

    def ignored(self, name):
        return any(fnmatch.fnmatchcase(name, pat) for pat in self.patterns())

    def test_media_extensions_ignored_in_any_case(self):
        for ext in self.REQUIRED:
            for variant in (ext, ext.upper(), ext.capitalize()):
                self.assertTrue(self.ignored(f"file.{variant}"), variant)

    def test_project_files_not_ignored(self):
        for name in ("README.md", "ideas.csv", "project.json", "script.md", "cli.py", "shotlist.csv",
                     "register.csv", "subtitles.srt"):
            self.assertFalse(self.ignored(name), name)

    def test_secrets_ignored(self):
        self.assertIn(".env", self.patterns())

    @unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "git not available")
    def test_git_agrees(self):
        paths = ["assets/brand/logo.png", "brands/qhaze/en/x/06_visuals/thumb.JPG",
                 "brands/qhaze/en/x/07_edit/final.webm", "a/b.AVI", "design.psd"]
        out = subprocess.run(["git", "check-ignore", *paths], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.stdout.split(), paths)
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertEqual([t for t in tracked if self.ignored(t.rsplit("/", 1)[-1])], [])


# ------------------------------------------------------------------- 4 (LOW)
class TestLanguageValidation(Base):
    def test_invalid_lang_rejected_everywhere(self):
        for argv in (["status", "--lang", "fr"], ["ideas", "--lang", "fr"], ["ideas", "list", "--lang", "xx"],
                     ["publish", "--lang", "fr"], ["publish", "list", "--lang", "fr"],
                     ["analytics", "report", "--lang", "fr"], ["new", "T", "--lang", "fr", "--division", "gaming"],
                     ["ideas", "add", "T", "--lang", "fr", "--division", "gaming"], ["status", "--lang", ""]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("Unknown language", out, argv)
            self.assertIn("en (English), ms (Bahasa Melayu)", out, argv)

    def test_valid_lang_case_insensitive(self):
        create_project(self.ctx, "Malay one", "ms", "gaming", created="2026-01-01")
        code, out = self.cli("status", "--lang", "MS")
        self.assertEqual(code, 0, out)
        self.assertIn("malay-one", out)
        code, out = self.cli("ideas", "add", "Ujian", "--lang", " Ms ", "--division", "gaming")
        self.assertEqual(code, 0, out)
        self.assertIn("MS-", out)


# ------------------------------------------------------------------- 5 (LOW)
class TestPublishingAnalyticsValidation(Base):
    def setUp(self):
        super().setUp()
        self.p = create_project(self.ctx, "Pub test", "en", "gaming", created="2026-01-01")
        while self.p.stage != "publish":
            advance(self.ctx, self.p, force=True)

    def test_platform_names(self):
        self.assertEqual(check_platform(self.ctx, "TikTok"), "tiktok")
        self.assertEqual(check_platform(self.ctx, "YouTube Shorts"), "youtube_shorts")
        self.assertEqual(check_platform(self.ctx, "instagram-reels"), "instagram_reels")
        for bad in ("myspace", "", None, "youtube2"):
            with self.assertRaises(FactoryError):
                check_platform(self.ctx, bad)

    def test_urls(self):
        good = [("youtube", "https://www.youtube.com/watch?v=abc"), ("youtube", "https://youtu.be/abc"),
                ("youtube_shorts", "https://m.youtube.com/shorts/abc"), ("tiktok", "https://vm.tiktok.com/ZMabc/"),
                ("instagram_reels", "https://www.instagram.com/reel/abc/"), ("facebook", "https://fb.watch/abc"),
                ("facebook_reels", "http://facebook.com/reel/1")]
        for platform, url in good:
            self.assertEqual(check_url(self.ctx, url, platform), url)
        bad = [("youtube", "not-a-url"), ("youtube", "youtube.com/watch?v=1"), ("youtube", "ftp://youtube.com/x"),
               ("youtube", "https://www.tiktok.com/@a/video/1"), ("youtube", "https://notyoutube.com/x"),
               ("youtube", "https://youtube.com.evil.example/x"), ("tiktok", "https://www.tiktok.com/a b"),
               ("tiktok", ""), ("tiktok", "https:///video")]
        for platform, url in bad:
            with self.assertRaises(FactoryError, msg=url):
                check_url(self.ctx, url, platform)

    def test_publish_record_rules(self):
        code, out = self.cli("publish", "record", "pub-test", "--platform", "TikTok",
                             "--url", "https://www.tiktok.com/@q/video/1", "--date", "2026-01-02")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.p.__class__.load(self.p.folder).meta["publications"][0]["platform"], "tiktok")
        for argv, msg in (
                (["--platform", "myspace", "--url", "https://myspace.com/x"], "Unknown platform"),
                (["--platform", "youtube", "--url", "www.youtube.com/watch?v=1"], "https://"),
                (["--platform", "youtube", "--url", "https://www.tiktok.com/@q/video/2"], "not a YouTube link"),
                (["--platform", "tiktok", "--url", "https://www.tiktok.com/@q/video/1/"], "already recorded"),
                (["--platform", "youtube", "--url", "https://youtu.be/x", "--date", "20-11-2026"], "YYYY-MM-DD"),
                (["--platform", "youtube", "--url", "https://youtu.be/x", "--date", "2999-01-01"], "future")):
            code, out = self.cli("publish", "record", "pub-test", *argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(msg, out, argv)

    def test_analytics_rules(self):
        with self.assertRaises(FactoryError) as e:
            analytics.add_snapshot(self.ctx, self.p, "youtube", views=10)
        self.assertIn("no publication recorded", str(e.exception))
        publishing.record_publication(self.ctx, self.p, "youtube", "https://youtu.be/abc", "2026-01-02")
        for argv, msg in ((["--platform", "myspace", "--views", "1"], "Unknown platform"),
                          (["--platform", "tiktok", "--views", "1"], "no publication recorded on 'tiktok'"),
                          (["--platform", "youtube", "--views", "-1"], "--views must be 0 or more"),
                          (["--platform", "youtube", "--ctr", "101"], "--ctr must be between 0 and 100"),
                          (["--platform", "youtube", "--subs", "-2"], "--subs must be 0 or more")):
            code, out = self.cli("analytics", "add", "pub-test", *argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(msg, out, argv)
        code, out = self.cli("analytics", "add", "pub-test", "--platform", "YouTube", "--views", "0", "--ctr", "100")
        self.assertEqual(code, 0, out)
        self.assertEqual(read_csv(analytics.perf_path(self.ctx, self.p))[0]["platform"], "youtube")


class TestPlatformConfigConsistency(unittest.TestCase):
    """Committed data uses only known platforms and valid URLs."""

    def test_config_and_sample_data(self):
        from factory.core.config import Context
        ctx = Context()
        platforms = ctx.config.platforms
        for fmt in ctx.config.formats.values():
            self.assertTrue(set(fmt["platforms"]) <= set(platforms), fmt["platforms"])
        for brand in ctx.config.brand_ids():
            for channel in ctx.config.brand(brand)["channels"]:
                self.assertTrue(set(channel["platforms"]) <= set(platforms), channel["platforms"])
        for p in iter_projects(ctx):
            for pub in p.meta.get("publications", []):
                check_url(ctx, pub["url"], check_platform(ctx, pub["platform"]))
        self.assertEqual(ctx.warnings, {})


if __name__ == "__main__":
    unittest.main()
