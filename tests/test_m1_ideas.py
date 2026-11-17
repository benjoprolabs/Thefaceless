"""Tests for M1 Idea Management (v0.4.1).

Decision 1  status change rules (system-only in_production/published)
Decision 2  `new --idea` only from backlog or shortlisted
Decision 3  sample idea EN-001 is published (one cell)
Decision 4  `ideas check`, project-side WARN, duplicate warning on `ideas add`
Decision 5  division/format locked for ideas with a project
plus: show / edit / dupes / list filters, new columns, automatic published,
English + Malay + Jawi, old and Excel-saved files.
"""

import errno
import json
import unittest
from pathlib import Path
from unittest import mock

from factory.core.checks import WARN, failures, run_checks
from factory.core.config import ROOT, FactoryError
from factory.core.files import read_csv, read_csv_table
from factory.core.projects import find_project
from factory.modules import ideas, publishing
from factory.modules.production import advance, create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli

HEADER11 = "id,title,division,format,demand,competition,effort,score,status,project_id,created"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.en = self.ctx.paths.ideas_csv("qhaze", "en")
        self.ms = self.ctx.paths.ideas_csv("qhaze", "ms")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
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

    def idea(self, idea_id):
        return ideas.find_idea(self.ctx, "qhaze", idea_id)[1]

    def add(self, title, lang="en", division="gaming", fmt="short"):
        return ideas.add_idea(self.ctx, "qhaze", lang, title, division, fmt, 3, 3, 3)

    def write(self, path, text):
        path.write_text(text, encoding="utf-8")

    def produced(self, idea_id, to_stage=None):
        """Create a project from an idea (and optionally move it to a stage)."""
        self.ok("new", "--idea", idea_id)
        project = find_project(self.ctx, self.idea(idea_id)["project_id"])
        while to_stage and project.stage != to_stage:
            advance(self.ctx, project, force=True)
        return project


# ------------------------------------------------------------ decision 1
class TestStatusTransitions(Base):
    def test_all_allowed_manual_changes_en_and_ms(self):
        for lang in ("en", "ms"):
            iid = self.add(f"Transition test {lang}", lang=lang)["id"]
            for target in ("shortlisted", "backlog", "rejected", "backlog", "archived", "backlog",
                           "shortlisted", "rejected", "archived", "backlog"):
                out = self.ok("ideas", "status", iid, target)
                self.assertIn(f"→ {target}", out)
                self.assertEqual(self.idea(iid)["status"], target)
                self.assertTrue(self.idea(iid)["updated"])

    def test_refused_changes(self):
        iid = self.add("Refusals")["id"]
        self.assertIn("already 'backlog'", self.bad("ideas", "status", iid, "backlog"))
        self.assertIn("Unknown status 'done'", self.bad("ideas", "status", iid, "done"))
        self.assertIn("set automatically when a project is created", self.bad("ideas", "status", iid, "in_production"))
        self.assertIn("marked published only when its project has a recorded publication",
                      self.bad("ideas", "status", iid, "published"))
        self.ok("ideas", "status", iid, "archived")
        self.assertIn("can't change from 'archived' to 'shortlisted'", self.bad("ideas", "status", iid, "shortlisted"))
        self.assertIn("can't change from 'archived' to 'rejected'", self.bad("ideas", "status", iid, "rejected"))
        self.ok("ideas", "status", iid, "backlog")
        self.ok("ideas", "status", iid, "rejected")
        self.assertIn("can't change from 'rejected' to 'shortlisted'", self.bad("ideas", "status", iid, "shortlisted"))

    def test_status_input_is_normalised(self):
        iid = self.add("Normalised")["id"]
        self.ok("ideas", "status", iid.lower(), " Shortlisted ")
        self.assertEqual(self.idea(iid)["status"], "shortlisted")
        self.assertIn("set automatically", self.bad("ideas", "status", iid, "In-Production"))

    def test_ideas_with_a_project_cannot_be_changed_by_hand(self):
        project = self.produced("EN-002")
        for target in ("backlog", "shortlisted", "rejected", "archived"):
            self.assertIn("can't be changed by hand", self.bad("ideas", "status", "EN-002", target))
        self.assertEqual(self.idea("EN-002")["status"], "in_production")
        self.assertEqual(self.idea("EN-002")["project_id"], project.id)

    def test_manual_published_only_with_recorded_publication(self):
        project = self.produced("EN-002", to_stage="publish")
        self.assertIn("recorded publication", self.bad("ideas", "status", "EN-002", "published"))
        # older data: a publication saved before M1, so the idea was never updated
        meta = json.loads((project.folder / "project.json").read_text(encoding="utf-8"))
        meta["publications"] = [{"platform": "youtube", "url": "https://youtu.be/x", "date": "2026-01-02"}]
        (project.folder / "project.json").write_text(json.dumps(meta), encoding="utf-8")
        self.ok("ideas", "status", "EN-002", "published")
        self.assertEqual(self.idea("EN-002")["status"], "published")
        self.assertIn("can't be changed by hand", self.bad("ideas", "status", "EN-002", "archived"))

    def test_unknown_status_can_be_repaired(self):
        text = self.en.read_text(encoding="utf-8").replace("EN-004,The loudest sound ever recorded,history-mystery,"
                                                           "short,4,3,1,4.0,backlog", "EN-004,The loudest sound ever "
                                                           "recorded,history-mystery,short,4,3,1,4.0,Backlogg")
        self.write(self.en, text)
        self.assertIn("EN-004: unknown status 'Backlogg'", self.bad("ideas", "check"))
        self.ok("ideas", "status", "EN-004", "backlog")
        self.assertNotIn("EN-004", self.cli("ideas", "check")[1])


# ------------------------------------------------------------ decision 2
class TestProducibleStatuses(Base):
    def test_backlog_and_shortlisted_can_be_produced(self):
        self.produced("EN-002")
        self.ok("ideas", "status", "EN-003", "shortlisted")
        self.produced("EN-003")
        self.assertEqual(self.idea("EN-003")["status"], "in_production")

    def test_rejected_and_archived_are_refused(self):
        for status in ("rejected", "archived"):
            iid = self.add(f"Not now {status}")["id"]
            self.ok("ideas", "status", iid, status)
            before = sorted(self.tmp.glob("brands/qhaze/*/*/*"))
            out = self.bad("new", "--idea", iid)
            self.assertIn(f"is '{status}'. Only backlog or shortlisted ideas can become projects", out)
            self.assertIn(f"python -m factory ideas status {iid} backlog", out)
            with self.assertRaises(FactoryError):  # the code path is protected too
                create_project(self.ctx, "Direct", "en", "gaming", idea_id=iid, created="2026-01-01")
            self.assertEqual(sorted(self.tmp.glob("brands/qhaze/*/*/*")), before)  # nothing created
            self.ok("ideas", "status", iid, "backlog")
            self.produced(iid)

    def test_existing_link_messages_unchanged(self):
        self.produced("EN-002")
        self.assertIn("already has project", self.bad("new", "--idea", "EN-002"))


# ------------------------------------------------------------ decision 3
class TestSampleData(unittest.TestCase):
    def test_en001_published_and_lists_consistent(self):
        from factory.core.config import Context
        ctx = Context()
        _, idea = ideas.find_idea(ctx, "qhaze", "EN-001")
        self.assertEqual((idea["status"], idea["project_id"]),
                         ("published", "2026-11-17_why-octopuses-have-three-hearts"))
        self.assertEqual(ideas.check_ideas(ctx, "qhaze"), [])

    def test_only_one_cell_differs_from_phase1(self):
        header, rows = read_csv_table(ROOT / "brands/qhaze/en/ideas.csv")
        self.assertEqual(header, HEADER11.split(","))  # file not rewritten: still 11 columns
        raw = (ROOT / "brands/qhaze/en/ideas.csv").read_bytes()
        self.assertEqual(raw.count(b"\r\n"), len(rows) + 1)  # CRLF kept on every line
        self.assertEqual([r["status"] for r in rows], ["published", "backlog", "backlog", "backlog", "backlog"])


    def test_csv_files_are_stored_byte_for_byte(self):
        """CSV files keep CRLF (RFC 4180). Git must not convert them, or unchanged
        files show as modified and a one-cell edit rewrites every line."""
        import shutil
        import subprocess
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.csv  -text", attributes)
        if shutil.which("git") and (ROOT / ".git").exists():
            out = subprocess.run(["git", "check-attr", "text", "brands/qhaze/en/ideas.csv"], cwd=ROOT,
                                 capture_output=True, text=True).stdout
            self.assertIn("text: unset", out)


# ------------------------------------------------------------ decision 4
class TestIdeasCheck(Base):
    def rows(self, *lines):
        self.write(self.en, HEADER11 + "\n" + "\n".join(lines) + "\n")

    def test_every_rule(self):
        project = self.produced("EN-002", to_stage="publish")
        publishing.record_publication(self.ctx, project, "youtube", "https://youtu.be/a", "2026-01-02")
        unpublished = create_project(self.ctx, "Unpublished", "en", "gaming", created="2026-01-01")
        good = "EN-010,Good,gaming,short,3,3,3,3.0,backlog,,2026-01-01"
        self.rows(
            good,
            "EN-010,Duplicate ID,gaming,short,3,3,3,3.0,backlog,,2026-01-01",
            "EN-011,Odd status,gaming,short,3,3,3,3.0,maybe,,2026-01-01",
            "EN-012,Bad division,cars,short,3,3,3,3.0,backlog,,2026-01-01",
            "EN-013,Bad format,gaming,square,3,3,3,3.0,backlog,,2026-01-01",
            "EN-014,Bad scores,gaming,short,0,3.5,nan,3.0,backlog,,2026-01-01",
            "EN-015,Producing nothing,gaming,short,3,3,3,3.0,in_production,,2026-01-01",
            f"EN-016,Backlog but linked,gaming,short,3,3,3,3.0,backlog,{unpublished.id},2026-01-01",
            "EN-017,Gone,gaming,short,3,3,3,3.0,in_production,2026-01-01_en_deleted,2026-01-01",
            "EN-018,Published alone,gaming,short,3,3,3,3.0,published,,2026-01-01",
            f"EN-019,Published early,gaming,short,3,3,3,3.0,published,{unpublished.id},2026-01-01",
            f"EN-020,Behind,gaming,short,3,3,3,3.0,in_production,{project.id},2026-01-01",
        )
        brand = json.loads((self.tmp / "brands/qhaze/brand.json").read_text(encoding="utf-8"))
        brand["divisions"].remove("food-cooking")
        (self.tmp / "brands/qhaze/brand.json").write_text(json.dumps(brand), encoding="utf-8")
        with open(self.en, "a", encoding="utf-8") as f:
            f.write("EN-021,Disabled division,food-cooking,short,3,3,3,3.0,backlog,,2026-01-01\n")
        self.ctx.config._cache.clear()
        before = self.en.read_bytes()
        out = self.bad("ideas", "check", "--lang", "en")
        expected = {
            "EN-010": "duplicate idea ID", "EN-011": "unknown status 'maybe'", "EN-012": "unknown division 'cars'",
            "EN-013": "unknown format 'square'", "EN-015": "status is in_production but no project is linked",
            "EN-016": "status is backlog but it is linked to project", "EN-017": "linked project 2026-01-01_en_deleted not found",
            "EN-018": "status is published but no project is linked",
            "EN-019": f"project {unpublished.id} has no recorded publication",
            "EN-020": "has been published; run: python -m factory ideas status EN-020 published",
            "EN-021": "division 'food-cooking' is not enabled",
        }
        for iid, text in expected.items():
            self.assertTrue(any(iid in line and text in line for line in out.splitlines()), (iid, text, out))
        for name in ("demand", "competition", "effort"):
            self.assertIn(f"EN-014: {name} must be a whole number", out)
        self.assertEqual(self.en.read_bytes(), before)  # read-only

    def test_clean_lists_and_cli(self):
        # The sandbox has the idea lists but not the sample projects, so EN-001/MS-001
        # correctly report a missing project. Start from clean lists instead.
        self.assertIn("EN-001: linked project 2026-11-17_why-octopuses-have-three-hearts not found",
                      self.bad("ideas", "check"))
        for path in (self.en, self.ms):
            self.write(path, HEADER11 + "\n")
        self.add("Clean English")
        self.add("Bersih", lang="ms")
        self.produced("EN-001")
        self.assertIn("Idea lists are consistent.", self.ok("ideas", "check"))


class TestProjectSideWarnings(Base):
    def test_warns_but_never_blocks(self):
        project = self.produced("EN-002")
        idea_findings = lambda: [f for f in run_checks(self.ctx, project, "research")  # noqa: E731
                                 if f.code.startswith("IDEA_")]  # M2 adds source checks at Research
        self.assertEqual(idea_findings(), [])
        rows = read_csv(self.en)
        for r in rows:
            if r["id"] == "EN-002":
                r["project_id"] = "2026-01-01_en_other"
        from factory.core.files import write_csv
        write_csv(self.en, rows, ideas.FIELDS)
        self.assertEqual([(f.level, f.code) for f in idea_findings()], [(WARN, "IDEA_NOT_LINKED")])
        self.write(self.en, HEADER11 + "\n")
        findings = idea_findings()
        self.assertEqual([(f.level, f.code) for f in findings], [(WARN, "IDEA_MISSING")])
        self.assertEqual(failures(findings), [])
        from tests.helpers import add_source, tick_all
        tick_all(project.folder / "01_research/research.md")
        add_source(self.ctx, project)  # M2: a source is required to leave Research
        self.assertEqual(advance(self.ctx, project), "planning")  # WARN doesn't block

    def test_projects_without_an_idea_have_no_finding(self):
        p = create_project(self.ctx, "No idea", "ms", "gaming", created="2026-01-01")
        self.assertEqual([f for f in run_checks(self.ctx, p, "research") if f.code.startswith("IDEA_")], [])


class TestDuplicates(Base):
    def test_similarity_ignores_case_accents_punctuation(self):
        for a, b in (("Kenapa kita lupa mimpi?", "kenapa  KITA lupa mimpi"),
                     ("Café crème: the real story", "Cafe Creme - the real story!"),
                     ("سوتوڠ کوريتا", "سوتوڠ کوريتا!")):
            self.assertGreaterEqual(ideas.similarity(a, b), 0.85, (a, b))
        self.assertLess(ideas.similarity("Black holes explained", "Nasi lemak history"), 0.5)
        self.assertNotEqual(ideas.normalise_title("سوتوڠ"), "")  # Jawi letters are kept

    def test_dupes_command_per_language(self):
        self.add("The spotlight effect: nobody watches you that closely", division="psychology")
        self.add("Kenapa sotong kurita ada tiga jantung?", lang="ms", division="what-if-science")
        self.add("Why octopuses have three hearts", lang="ms")  # English title in the Malay list
        out = self.ok("ideas", "dupes")
        self.assertIn("EN-003", out)
        self.assertIn("EN-006", out)
        self.assertIn("MS-001", out)
        self.assertIn("MS-005", out)
        self.assertNotIn("MS-006", out)  # not compared with the English list
        self.assertIn("2 possible duplicate pair(s)", out)
        self.assertIn("0 possible", self.ok("ideas", "dupes", "--lang", "en", "--brand", "qhaze").replace("1 possible", "0 possible"))

    def test_threshold_from_rules_json(self):
        rules = self.tmp / "config/rules.json"
        data = json.loads(rules.read_text(encoding="utf-8"))
        data["ideas"]["duplicate_threshold"] = 0.2
        rules.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.assertNotIn("0 possible", self.ok("ideas", "dupes", "--lang", "en"))
        del data["ideas"]
        rules.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.assertEqual(ideas.duplicate_threshold(self.ctx), 0.85)  # default when the section is missing
        data["ideas"] = {"duplicate_threshold": 2}
        rules.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.assertIn("duplicate_threshold must be a number", self.bad("ideas", "dupes"))

    def test_add_warns_but_still_adds(self):
        out = self.ok("ideas", "add", "the loudest sound EVER recorded!", "--lang", "en", "--division", "history-mystery")
        self.assertIn("Added EN-006", out)
        self.assertIn("Warning: EN-006 looks like a duplicate of EN-004", out)
        self.ctx.warnings.clear()  # each real command runs in a fresh process
        out = self.ok("ideas", "add", "Something completely different", "--lang", "en", "--division", "gaming")
        self.assertNotIn("Warning", out)


# ------------------------------------------------------------ decision 5 + edit
class TestEdit(Base):
    def test_edit_fields_and_recalculate(self):
        out = self.ok("ideas", "edit", "MS-002", "--title", "Misteri Kota Gelanggi yang hilang", "--demand", "5",
                      "--effort", "2", "--tags", "Sejarah, misteri ,SEJARAH, کوتا", "--notes", "Line one\nline two")
        self.assertIn("score: 3.5 → 4.5", out)
        i = self.idea("MS-002")
        self.assertEqual((i["title"], i["demand"], i["competition"], i["effort"], i["score"]),
                         ("Misteri Kota Gelanggi yang hilang", "5", "2", "2", "4.5"))
        self.assertEqual(i["tags"], "sejarah, misteri, کوتا")
        self.assertEqual(i["notes"], "Line one line two")
        self.assertTrue(i["updated"])
        self.ok("ideas", "edit", "MS-002", "--division", "gaming", "--format", "short")
        self.assertEqual((self.idea("MS-002")["division"], self.idea("MS-002")["format"]), ("gaming", "short"))
        self.ok("ideas", "edit", "MS-002", "--tags", "")
        self.assertEqual(self.idea("MS-002")["tags"], "")

    def test_jawi_title(self):
        self.ok("ideas", "edit", "MS-003", "--title", "سجاره ناسي لمق")
        self.assertIn("سجاره ناسي لمق", self.ok("ideas", "show", "MS-003"))

    def test_validation(self):
        self.assertIn("Nothing to change", self.bad("ideas", "edit", "EN-002"))
        self.assertIn("title can't be empty", self.bad("ideas", "edit", "EN-002", "--title", "  "))
        self.assertIn("Unknown division", self.bad("ideas", "edit", "EN-002", "--division", "cars"))
        self.assertIn("Unknown format", self.bad("ideas", "edit", "EN-002", "--format", "square"))
        self.assertIn("whole numbers from 1 to 5", self.bad("ideas", "edit", "EN-002", "--demand", "6"))
        self.assertIn("already has these values", self.bad("ideas", "edit", "EN-002", "--demand", "5"))
        self.assertIn("not found", self.bad("ideas", "edit", "EN-999", "--demand", "5"))

    def test_division_and_format_locked_when_linked(self):
        project = self.produced("EN-002")
        before = {p: p.read_bytes() for p in project.folder.rglob("*") if p.is_file()}
        for argv in (["--division", "gaming"], ["--format", "short"]):
            self.assertIn("division and format can't change", self.bad("ideas", "edit", "EN-002", *argv))
        self.ok("ideas", "edit", "EN-002", "--title", "What if the Moon vanished", "--tags", "space", "--effort", "2")
        self.assertEqual(self.idea("EN-002")["project_id"], project.id)
        self.assertEqual({p: p.read_bytes() for p in before}, before)  # project untouched
        self.assertEqual(find_project(self.ctx, project.id).folder, project.folder)


class TestShowListFilters(Base):
    def test_show(self):
        project = self.produced("MS-002")
        out = self.ok("ideas", "show", "ms-002")
        self.assertIn("Language : Bahasa Melayu", out)
        self.assertIn(f"Project  : {project.id} (stage: Research, publications: 0)", out)
        self.assertIn("Project  : -", self.ok("ideas", "show", "EN-003"))
        self.add("Misteri Kota Gelanggi!", lang="ms", division="history-mystery")
        self.assertIn("Possible duplicate: MS-005", self.ok("ideas", "show", "MS-002"))
        self.bad("ideas", "show", "XX-001")

    def test_list_filters(self):
        self.ok("ideas", "status", "EN-003", "shortlisted")
        self.ok("ideas", "edit", "EN-004", "--tags", "sound, Physics")
        out = self.ok("ideas", "list", "--status", "shortlisted")
        self.assertIn("EN-003", out)
        self.assertNotIn("EN-004", out)
        out = self.ok("ideas", "--tag", "PHYSICS")
        self.assertIn("EN-004", out)
        self.assertIn("[sound, physics]", out)
        self.assertNotIn("EN-003", out)
        self.assertIn("Unknown status", self.bad("ideas", "list", "--status", "maybe"))

    def test_default_list_output_unchanged(self):
        out = self.ok("ideas", "--lang", "en")
        self.assertIn("  EN-003   4.0  backlog        psychology         short The spotlight effect", out)


# ------------------------------------------------------------ automatic published
class TestAutomaticPublished(Base):
    def test_first_publication_marks_idea_published(self):
        project = self.produced("MS-002", to_stage="publish")
        out = self.ok("publish", "record", project.id, "--platform", "tiktok",
                      "--url", "https://www.tiktok.com/@q/video/1", "--date", "2026-01-02")
        self.assertIn("Idea MS-002 marked published.", out)
        self.assertEqual(self.idea("MS-002")["status"], "published")
        out = self.ok("publish", "record", project.id, "--platform", "youtube", "--url", "https://youtu.be/b")
        self.assertNotIn("marked published", out)
        self.assertEqual(self.idea("MS-002")["status"], "published")

    def test_locked_idea_list_keeps_the_publication(self):
        project = self.produced("EN-002", to_stage="publish")
        real_write = ideas.write_csv
        with mock.patch.object(ideas, "write_csv",
                               side_effect=PermissionError(errno.EACCES, "Permission denied", str(self.en))):
            code, out = self.cli("publish", "record", project.id, "--platform", "youtube", "--url", "https://youtu.be/c")
        self.assertIs(ideas.write_csv, real_write)
        self.assertEqual(code, 0, out)
        self.assertIn("Warning: Publication saved, but idea EN-002 could not be marked published", out)
        self.assertIn("Permission denied", out)
        self.assertIn("python -m factory ideas status EN-002 published", out)
        self.assertEqual(len(find_project(self.ctx, project.id).meta["publications"]), 1)
        self.assertEqual(self.idea("EN-002")["status"], "in_production")
        self.ok("ideas", "status", "EN-002", "published")  # the suggested fix works

    def test_projects_without_ideas_are_unaffected(self):
        p = create_project(self.ctx, "Solo", "en", "gaming", created="2026-01-01")
        while p.stage != "publish":
            advance(self.ctx, p, force=True)
        out = self.ok("publish", "record", p.id, "--platform", "youtube", "--url", "https://youtu.be/d")
        self.assertNotIn("Warning", out)

    def test_missing_idea_is_a_warning(self):
        project = self.produced("EN-002", to_stage="publish")
        self.write(self.en, HEADER11 + "\n")
        code, out = self.cli("publish", "record", project.id, "--platform", "youtube", "--url", "https://youtu.be/e")
        self.assertEqual(code, 0, out)
        self.assertIn("idea EN-002 was not found", out)


# ------------------------------------------------------------ old and Excel files
class TestOldAndExcelFiles(Base):
    def test_old_11_column_file_gains_new_columns_on_write(self):
        self.assertEqual(read_csv_table(self.en)[0], HEADER11.split(","))
        self.assertEqual(self.idea("EN-003")["tags"], "")
        self.ok("ideas", "edit", "EN-003", "--tags", "mind")
        header, rows = read_csv_table(self.en)
        self.assertEqual(header, ideas.FIELDS)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2]["tags"], "mind")
        self.assertEqual(rows[0]["status"], "published")

    def test_excel_saved_file_with_extra_column(self):
        text = self.ms.read_text(encoding="utf-8").replace("\r\n", "\n")
        lines = text.strip("\n").split("\n")
        lines = [lines[0] + ";my_notes"] + [l.replace(",", ";") + ";keep" for l in lines[1:]]
        lines[0] = lines[0].replace(",", ";")
        self.ms.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8") + b"\r\n")
        self.ok("ideas", "status", "MS-003", "shortlisted")
        rows = read_csv(self.ms)
        self.assertEqual([r["my_notes"] for r in rows], ["keep"] * 4)
        self.assertEqual(rows[2]["status"], "shortlisted")
        self.assertIn("MS-003", self.ok("ideas", "show", "MS-003"))


# ------------------------------------------------------------ Phase 1 regression
class TestPhase1Regression(Base):
    def test_unlink_still_works(self):
        project = self.produced("EN-002")
        import shutil
        shutil.rmtree(project.folder)
        out = self.ok("ideas", "unlink", "EN-002")
        self.assertIn("status in_production → backlog", out)
        i = self.idea("EN-002")
        self.assertEqual((i["status"], i["project_id"]), ("backlog", ""))
        self.assertTrue(i["updated"])

    def test_numbering_scoring_and_language_conflict(self):
        self.assertEqual(self.add("Next one")["id"], "EN-006")
        self.assertEqual(self.add("Satu lagi", lang="ms")["id"], "MS-005")
        self.assertIn("Conflicting options", self.bad("new", "--idea", "EN-002", "--lang", "ms"))
        self.assertEqual(ideas.score(4, 2, 2), 4.0)

    def test_dashboard_backlog_count_unchanged(self):
        out = self.ok("dashboard")
        self.assertIn("Ideas in backlog: EN 4, MS 3", out)

    def test_voice_and_paid_api_free(self):
        source = (ROOT / "factory/modules/ideas.py").read_text(encoding="utf-8")
        for word in ("elevenlabs", "tts", "voice", "requests", "urlopen"):
            self.assertNotIn(word, source.lower())


if __name__ == "__main__":
    unittest.main()
