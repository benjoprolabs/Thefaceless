"""Tests for M2 Research Engine (v0.4.2).

sources.csv: add / list / verify / check / copy-sources, every §7 Research
rule (passing and failing), the Research gate, format 3 + migrate, and the
three approved decisions:
  1. missing/empty sources: FAIL while at Research, WARN after it
  2. new research.md points to sources.csv; existing files untouched
  3. copy-sources keeps verification_status, accessed and published exactly
"""

import hashlib
import json
import shutil
import unittest
from datetime import date, timedelta

from factory.core.checks import FAIL, WARN, failures, run_checks
from factory.core.config import ROOT, Context, FactoryError
from factory.core.files import read_csv, read_csv_table, today
from factory.core.projects import CURRENT_SCHEMA, find_project, iter_projects
from factory.modules import research
from factory.modules.production import advance, create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli, tick_all

HEADER = "id,title,url,publisher,type,published,accessed,verification_status,reliability,notes"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = create_project(self.ctx, "Research test", "en", "psychology", created="2026-01-01")
        self.csv = research.sources_path(self.ctx, self.p)

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        self.ctx.warnings.clear()  # each real command runs in a fresh process
        return run_cli(list(argv), self.ctx)

    def ok(self, *argv):
        code, out = self.cli(*argv)
        self.assertEqual(code, 0, f"{argv}\n{out}")
        return out

    def bad(self, *argv):
        code, out = self.cli(*argv)
        self.assertEqual(code, 1, f"{argv}\n{out}")
        self.assertNotIn("Traceback", out)
        return out

    def add(self, project=None, title="A study", url="https://www.example.org/a", kind="study",
            accessed="today", **kw):
        return research.add_source(self.ctx, project or self.p, title, url, kind, accessed, **kw)[0]

    def rows(self, *lines, project=None):
        path = research.sources_path(self.ctx, project or self.p)
        path.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8")

    def codes(self, project=None):
        return [(f.level, f.code) for f in research.check_sources(self.ctx, project or self.p)]


# ---------------------------------------------------------------- sources.csv
class TestAddAndList(Base):
    def test_new_projects_get_sources_csv_with_all_columns(self):
        self.assertTrue(self.csv.exists())
        self.assertEqual(read_csv_table(self.csv)[0], HEADER.split(","))
        self.assertEqual(self.p.meta["schema_version"], CURRENT_SCHEMA)
        self.assertEqual(CURRENT_SCHEMA, 3)

    def test_add_sources_en_ms_jawi_and_offline(self):
        s1 = self.add(title="Gilovich spotlight study", publisher="APA", published="2000-02-01", reliability="5",
                      notes="line one\nline two")
        s2 = self.add(title="Buku sejarah Melayu", url="", kind="book", accessed="2025-12-01")
        ms = create_project(self.ctx, "Kajian", "ms", "history-mystery", created="2026-01-01")
        s3 = self.add(project=ms, title="سجاره ملايو", url="https://ms.wikipedia.org/wiki/Sejarah", kind="secondary")
        self.assertEqual((s1["id"], s2["id"], s3["id"]), ("S1", "S2", "S1"))
        rows = read_csv(self.csv)
        self.assertEqual(rows[0]["verification_status"], "unverified")
        self.assertEqual(rows[0]["accessed"], today())
        self.assertEqual((rows[0]["publisher"], rows[0]["published"], rows[0]["reliability"]), ("APA", "2000-02-01", "5"))
        self.assertEqual(rows[0]["notes"], "line one line two")
        self.assertEqual((rows[1]["url"], rows[1]["type"]), ("", "book"))
        self.assertEqual(read_csv(research.sources_path(self.ctx, ms))[0]["title"], "سجاره ملايو")
        self.assertEqual(self.codes(), [])
        out = self.ok("research", "sources", "research-test")
        self.assertIn("S1    unverified  study", out)
        self.assertIn("Buku sejarah Melayu", out)

    def test_ids_continue_after_excel_edits(self):
        self.rows("S1,a,,,book,,2026-01-01,verified,,", "S7,b,,,book,,2026-01-01,verified,,", "x,c,,,book,,2026-01-01,verified,,")
        self.assertEqual(self.add()["id"], "S8")

    def test_add_validation(self):
        for argv, msg in ((["--title", " ", "--type", "study", "--accessed", "today"], "--title is required"),
                          (["--title", "t", "--type", "blog", "--accessed", "today"], "type must be one of"),
                          (["--title", "t", "--type", "study", "--accessed", "2026-13-01"], "accessed: Invalid date"),
                          (["--title", "t", "--type", "study", "--accessed", "2999-01-01"], "is in the future"),
                          (["--title", "t", "--type", "study", "--accessed", "today", "--published", "2999-01-01"], "published"),
                          (["--title", "t", "--type", "study", "--accessed", "today", "--url", "example.org/x"], "https://"),
                          (["--title", "t", "--type", "study", "--accessed", "today", "--reliability", "6"], "reliability"),
                          (["--title", "t", "--type", "study", "--accessed", "today", "--reliability", "x"], "reliability")):
            self.assertIn(msg, self.bad("research", "add-source", "research-test", *argv), argv)
        self.assertEqual(read_csv(self.csv), [])  # nothing written by refused adds

    def test_duplicate_link_is_a_warning(self):
        self.add(url="https://www.example.org/a/")
        out = self.ok("research", "add-source", "research-test", "--title", "Same", "--type", "news",
                      "--url", "http://example.org/a", "--accessed", "today")
        self.assertIn("Added S2", out)
        self.assertIn("Warning: S2 has the same link as S1", out)
        self.assertIn((WARN, "SOURCE_DUPLICATE_URL"), self.codes())

    def test_excel_saved_file_and_extra_columns(self):
        lines = [HEADER.replace(",", ";") + ";my_col", "S1;Excel row;;;book;;2026-01-01;verified;4;;keep"]
        self.csv.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8") + b"\r\n")
        self.add(title="Second")
        rows = read_csv(self.csv)
        self.assertEqual([r["id"] for r in rows], ["S1", "S2"])
        self.assertEqual(rows[0]["my_col"], "keep")

    def test_damaged_file_is_reported(self):
        self.csv.write_text("id,title\nS1,x\n", encoding="utf-8")
        self.assertIn("is missing column(s)", self.bad("research", "sources", "research-test"))
        self.assertEqual(self.codes(), [(FAIL, "SOURCES_FILE")])


class TestVerify(Base):
    def test_statuses(self):
        self.add()
        for status in ("verified", "disputed", "outdated", "unverified"):
            self.assertIn(f"→ {status}", self.ok("research", "verify", "research-test", "s1", status.upper()))
            self.assertEqual(read_csv(self.csv)[0]["verification_status"], status)
        self.assertIn("already 'unverified'", self.bad("research", "verify", "research-test", "S1", "unverified"))
        self.assertIn("status must be one of", self.bad("research", "verify", "research-test", "S1", "maybe"))
        self.assertIn("Source 'S9' not found", self.bad("research", "verify", "research-test", "S9", "verified"))
        self.csv.unlink()
        self.assertIn("has no sources.csv", self.bad("research", "verify", "research-test", "S1", "verified"))


# ---------------------------------------------------------------- §7 rules
class TestRules(Base):
    GOOD = "S1,Good,https://example.org/a,Pub,study,2020-01-01,2026-01-01,verified,4,"

    def test_every_rule_fails_and_passes(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        cases = {
            "SOURCE_ACCESSED": "S1,t,,,book,,,verified,,",
            "SOURCE_ACCESSED ": f"S1,t,,,book,,{future},verified,,",
            "SOURCE_PUBLISHED": f"S1,t,,,book,{future},2026-01-01,verified,,",
            "SOURCE_TYPE": "S1,t,,,blog,,2026-01-01,verified,,",
            "SOURCE_VERIFICATION_STATUS": "S1,t,,,book,,2026-01-01,checked,,",
            "SOURCE_RELIABILITY": "S1,t,,,book,,2026-01-01,verified,9,",
            "SOURCE_TITLE": "S1,,,,book,,2026-01-01,verified,,",
            "SOURCE_URL": "S1,t,ftp://example.org/a,,book,,2026-01-01,verified,,",
            "SOURCE_ID": "X1,t,,,book,,2026-01-01,verified,,",
        }
        for code, line in cases.items():
            self.rows(line)
            self.assertIn((FAIL, code.strip()), self.codes(), line)
            self.rows(self.GOOD)
            self.assertEqual(self.codes(), [], code)
        self.rows(self.GOOD, "S1,dup,,,book,,2026-01-01,verified,,")
        self.assertIn((FAIL, "SOURCE_DUPLICATE_ID"), self.codes())
        self.rows(self.GOOD, "S2,again,https://www.example.org/a/,,news,,2026-01-01,verified,,")
        self.assertEqual(self.codes(), [(WARN, "SOURCE_DUPLICATE_URL")])

    def test_technology_ai_age_rule(self):
        tech = create_project(self.ctx, "AI tools", "en", "technology-ai", created="2026-01-01")
        old = (date.today() - timedelta(days=91)).isoformat()
        recent = (date.today() - timedelta(days=90)).isoformat()
        self.rows(f"S1,old,,,news,,{old},verified,,", project=tech)
        self.assertEqual(self.codes(tech), [(WARN, "SOURCE_OLD")])
        self.rows(f"S1,recent,,,news,,{recent},verified,,", project=tech)
        self.assertEqual(self.codes(tech), [])
        self.rows(f"S1,old,,,news,,{old},verified,,")  # psychology: no age rule
        self.assertEqual(self.codes(), [])
        cfg = self.tmp / "config/divisions.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data["technology-ai"]["source_max_age_days"] = 200
        cfg.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.rows(f"S1,old,,,news,,{old},verified,,", project=tech)
        self.assertEqual(self.codes(tech), [])  # age comes from divisions.json

    def test_check_command(self):
        self.add()
        self.assertIn("Sources OK.", self.ok("research", "check", "research-test"))
        self.rows("S1,t,,,blog,,2026-01-01,verified,,")
        self.assertIn("1 FAIL", self.bad("research", "check", "research-test"))


class TestGate(Base):
    def test_sources_required_to_leave_research(self):
        tick_all(self.p.folder / "01_research/research.md")
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        self.assertIn("SOURCES_EMPTY", str(e.exception))
        self.add()
        self.assertEqual(advance(self.ctx, self.p), "planning")

    def test_invalid_source_blocks_and_force_is_recorded(self):
        tick_all(self.p.folder / "01_research/research.md")
        self.rows("S1,t,,,blog,,2026-01-01,verified,,")
        with self.assertRaises(FactoryError):
            advance(self.ctx, self.p)
        advance(self.ctx, self.p, force=True)
        self.assertEqual(self.p.meta["history"][-1]["forced_findings"], ["SOURCE_TYPE"])


# ---------------------------------------------------------------- decision 1
class TestDecision1MissingSources(Base):
    def test_fail_at_research_warn_after(self):
        self.csv.unlink()
        self.assertEqual(self.codes(), [(FAIL, "SOURCES_MISSING")])
        self.assertIn("migrate --apply", research.check_sources(self.ctx, self.p)[0].message)
        advance(self.ctx, self.p, force=True)
        self.assertEqual(self.codes(), [(WARN, "SOURCES_MISSING")])
        self.csv.write_text(HEADER + "\n", encoding="utf-8")
        self.assertEqual(self.codes(), [(WARN, "SOURCES_EMPTY")])
        self.assertEqual(failures(run_checks(self.ctx, self.p, "research")), [])
        self.assertTrue(self.csv.exists())  # checks never create or change files

    def test_real_sample_projects_unchanged_and_without_fail(self):
        ctx = Context()
        octopus = find_project(ctx, "octopus")
        self.assertFalse(research.sources_path(ctx, octopus).exists())  # existing data not modified
        self.assertEqual([(f.level, f.code) for f in run_checks(ctx, octopus, "research")], [(WARN, "SOURCES_MISSING")])
        kenapa = find_project(ctx, "kenapa")  # still at Research: FAIL, as decided
        self.assertEqual([(f.level, f.code) for f in run_checks(ctx, kenapa, "research")], [(FAIL, "SOURCES_MISSING")])
        for p in (octopus, kenapa):
            self.assertEqual(p.meta["schema_version"], 1)


# ---------------------------------------------------------------- decision 2
class TestDecision2Template(Base):
    def test_new_research_md_points_to_sources_csv(self):
        text = (self.p.folder / "01_research/research.md").read_text(encoding="utf-8")
        self.assertIn("Sources are tracked in `sources.csv`", text)
        self.assertIn(f"research add-source {self.p.id}", text)
        self.assertNotIn("| # | Source | URL | Accessed | Notes |", text)
        self.assertIn("- [ ] At least 2 credible sources recorded", text)
        self.assertIn("- [ ] Competition checked", text)
        self.assertIn("- [ ] Pitch is clear in one sentence", text)

    def test_existing_research_md_files_not_rewritten(self):
        ctx = Context()
        for p in iter_projects(ctx):
            text = (p.folder / "01_research/research.md").read_text(encoding="utf-8")
            self.assertIn("| # | Source | URL | Accessed | Notes |", text, p.id)  # Phase 1 table still there

    def test_migrate_does_not_touch_research_md(self):
        old = self.tmp / "brands/qhaze/en/what-if-science"
        shutil.copytree(find_project(Context(), "octopus").folder, old / "2026-11-17_why-octopuses-have-three-hearts")
        md = old / "2026-11-17_why-octopuses-have-three-hearts/01_research/research.md"
        before = digest(md)
        self.ok("migrate", "--apply")
        self.assertEqual(digest(md), before)


# ---------------------------------------------------------------- decision 3
class TestDecision3CopySources(Base):
    def setUp(self):
        super().setUp()
        self.origin = create_project(self.ctx, "Origin", "en", "gaming", created="2026-01-01")
        self.rows("S1,Verified study,https://www.example.org/a,Pub,study,2019-05-01,2025-01-10,verified,5,keep",
                  "S2,Old book,,Penerbit,book,,2024-03-03,outdated,,",
                  "S3,Disputed claim,https://example.org/b,,news,,2025-06-06,disputed,2,",
                  project=self.origin)
        self.origin_csv = research.sources_path(self.ctx, self.origin)

    def test_values_kept_exactly_and_origin_untouched(self):
        before = digest(self.origin_csv)
        out = self.ok("research", "copy-sources", "research-test", "--from", "origin")
        self.assertIn("3 copied, 0 skipped", out)
        self.assertEqual(digest(self.origin_csv), before)
        copied = read_csv(self.csv)
        for old, new in zip(read_csv(self.origin_csv), copied):
            for field in ("title", "url", "publisher", "type", "published", "accessed",
                          "verification_status", "reliability", "notes"):
                self.assertEqual(new[field], old[field], field)
        self.assertNotIn(today(), [r["accessed"] for r in copied])  # not "freshly verified"

    def test_no_duplicates_and_new_ids(self):
        self.add(title="Mine", url="http://example.org/a/")  # same page as origin S1
        self.add(title="Old book", url="", kind="book", publisher="penerbit")  # same as origin S2 (no link)
        out = self.ok("research", "copy-sources", "research-test", "--from", "origin")
        self.assertIn("1 copied, 2 skipped", out)
        self.assertEqual([r["id"] for r in read_csv(self.csv)], ["S1", "S2", "S3"])
        self.assertIn("0 copied, 3 skipped", self.ok("research", "copy-sources", "research-test", "--from", "origin"))

    def test_across_languages_and_errors(self):
        ms = create_project(self.ctx, "Bahasa", "ms", "gaming", created="2026-01-01")
        self.assertIn("3 copied", self.ok("research", "copy-sources", ms.id, "--from", "origin"))
        self.assertIn("different project", self.bad("research", "copy-sources", "origin", "--from", "origin"))
        empty = create_project(self.ctx, "Empty", "en", "gaming", created="2026-01-01")
        self.assertIn("has no sources to copy", self.bad("research", "copy-sources", "origin", "--from", empty.id))


# ---------------------------------------------------------------- format 3 + migrate
class TestMigrateV3(Base):
    def setUp(self):
        super().setUp()
        for p in iter_projects(Context()):
            shutil.copytree(p.folder, self.tmp / p.folder.relative_to(ROOT))

    def test_adds_only_sources_csv_and_never_overwrites(self):
        self.assertIn("add 01_research/sources.csv", self.ok("migrate"))
        octopus = find_project(self.ctx, "octopus")
        self.assertFalse(research.sources_path(self.ctx, octopus).exists())  # preview wrote nothing
        mine = research.sources_path(self.ctx, self.p)
        self.add()
        mine_before = digest(mine)
        self.ok("migrate", "--apply")
        for p in iter_projects(self.ctx):
            self.assertEqual(p.meta["schema_version"], 3)
            self.assertTrue(research.sources_path(self.ctx, p).exists())
        self.assertEqual(digest(mine), mine_before)  # an existing sources.csv is never overwritten
        self.assertEqual(read_csv(research.sources_path(self.ctx, octopus)), [])
        self.assertIn("All projects are up to date (format 3)", self.ok("migrate"))


if __name__ == "__main__":
    unittest.main()
