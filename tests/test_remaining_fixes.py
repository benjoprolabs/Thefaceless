"""Regression tests for the remaining audit issues (v0.3.4).

B6  Deleting a stage folder / checklist file / checklist can't bypass the gate
B7  Unknown --brand and --division are clear errors (not empty lists)
B8  Accented and Jawi titles give readable, unique IDs; no same-day collisions
B9  The same title in English and Malay on the same day doesn't collide
B10 `ideas unlink` safely returns an idea to the backlog after its project was deleted
"""

import json
import shutil
import unittest

from factory.core.config import FactoryError
from factory.core.files import read_csv, slugify, title_slug
from factory.core.projects import iter_projects
from factory.modules import ideas
from factory.modules.production import advance, create_project, stage_blockers
from tests.helpers import make_sandbox, remove_sandbox, run_cli, tick_all


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        return run_cli(list(argv), self.ctx)

    def new(self, title, lang="en", division="psychology", created="2026-01-01"):
        return create_project(self.ctx, title, lang, division, created=created)


# ------------------------------------------------------------------ B6
class TestGateCannotBeBypassed(Base):
    def setUp(self):
        super().setUp()
        self.p = self.new("Gate test")

    def test_deleted_stage_folder_blocks_advance(self):
        shutil.rmtree(self.p.folder / "01_research")
        code, out = self.cli("advance", "gate-test")
        self.assertEqual(code, 1)
        self.assertIn("stage folder 01_research/ is missing", out)
        self.assertEqual(self.p.__class__.load(self.p.folder).meta["stage"], "research")

    def test_deleted_checklist_file_blocks_advance(self):
        (self.p.folder / "01_research/research.md").unlink()
        self.assertEqual(stage_blockers(self.ctx, self.p), ["research.md: file is missing. Restore it or use --force"])

    def test_one_of_two_stage_files_deleted(self):
        while self.p.stage != "visuals":
            advance(self.ctx, self.p, force=True)
        (self.p.folder / "06_visuals/visuals.md").unlink()
        self.assertIn("visuals.md: file is missing. Restore it or use --force", stage_blockers(self.ctx, self.p))

    def test_removed_checklist_section_blocks_advance(self):
        (self.p.folder / "01_research/research.md").write_text("# Research\nAll done, trust me.\n")
        self.assertEqual(stage_blockers(self.ctx, self.p),
                         ["research.md: the stage checklist was removed. Restore it or use --force"])

    def test_ticked_checklist_still_advances_and_force_still_works(self):
        tick_all(self.p.folder / "01_research/research.md")
        self.assertEqual(stage_blockers(self.ctx, self.p), [])
        self.assertEqual(advance(self.ctx, self.p), "planning")
        shutil.rmtree(self.p.folder / "02_planning")
        self.assertEqual(advance(self.ctx, self.p, force=True), "script")
        self.assertTrue(self.p.meta["history"][-1]["forced"])

    def test_sample_projects_unaffected(self):
        from factory.core.config import Context
        ctx = Context()
        for p in iter_projects(ctx):
            blockers = stage_blockers(ctx, p)
            self.assertFalse(any("missing" in b or "removed" in b for b in blockers), (p.id, blockers))


# ------------------------------------------------------------------ B7
class TestBrandAndDivisionValidation(Base):
    def test_unknown_brand_rejected(self):
        for argv in (["status", "--brand", "other"], ["ideas", "--brand", "other"], ["ideas", "list", "--brand", "x"],
                     ["niches", "--brand", "other"], ["publish", "--brand", "other"],
                     ["analytics", "report", "--brand", "other"], ["status", "--brand", ""]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("Unknown brand", out, argv)
            self.assertIn("Use one of: qhaze", out, argv)

    def test_unknown_division_rejected(self):
        for argv in (["status", "--division", "cars"], ["ideas", "--division", "cars"],
                     ["ideas", "list", "--division", "cars"], ["status", "--division", ""],
                     ["library", "visuals", "--division", "cars"]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("Unknown division", out, argv)
            self.assertIn("what-if-science, psychology", out, argv)

    def test_disabled_division_for_brand(self):
        brand_json = self.tmp / "brands/qhaze/brand.json"
        brand = json.loads(brand_json.read_text())
        brand["divisions"].remove("gaming")
        brand_json.write_text(json.dumps(brand))
        code, out = self.cli("status", "--division", "gaming")
        self.assertEqual(code, 1)
        self.assertIn("Division 'gaming' is not enabled for brand 'qhaze'", out)

    def test_valid_values_case_insensitive(self):
        self.new("Filter me", division="gaming")
        code, out = self.cli("status", "--brand", "QHAZE", "--division", "Gaming")
        self.assertEqual(code, 0, out)
        self.assertIn("filter-me", out)
        code, out = self.cli("ideas", "--division", "Psychology", "--lang", "en")
        self.assertEqual(code, 0, out)
        self.assertIn("EN-003", out)


# ------------------------------------------------------------------ B8
class TestIdGeneration(Base):
    def test_accents_transliterated(self):
        for title, expected in (("Café crème: 100% \"real\"?", "cafe-creme-100-real"),
                                ("Straße & Smørrebrød", "strasse-smorrebrod"),
                                ("Ünïcödé Ⅻ", "unicode-xii")):
            self.assertEqual(title_slug(title), expected)
        self.assertEqual(slugify("Café"), "cafe")

    def test_jawi_titles_are_distinct_and_stable(self):
        a, b = title_slug("سوتوڠ کوريتا"), title_slug("جانتوڠ تيݢ")
        self.assertRegex(a, r"^jawi-[0-9a-f]{6}$")
        self.assertNotEqual(a, b)
        self.assertEqual(a, title_slug("  سوتوڠ کوريتا "))
        self.assertRegex(title_slug("宇宙"), r"^title-[0-9a-f]{6}$")
        self.assertRegex(title_slug("!!!"), r"^title-[0-9a-f]{6}$")

    def test_mixed_latin_and_jawi_titles_do_not_collide(self):
        a, b = title_slug("Sejarah نسي لمق"), title_slug("Sejarah ريندڠ")
        self.assertTrue(a.startswith("sejarah-") and b.startswith("sejarah-"))
        self.assertNotEqual(a, b)

    def test_two_jawi_projects_same_day(self):
        p1 = self.new("سوتوڠ کوريتا", lang="ms", division="gaming")
        p2 = self.new("جانتوڠ تيݢ", lang="ms", division="gaming")
        self.assertNotEqual(p1.id, p2.id)
        self.assertTrue(p1.id.startswith("2026-01-01_ms_jawi-"))
        code, out = self.cli("show", p1.id)
        self.assertEqual(code, 0, out)
        self.assertIn("سوتوڠ کوريتا", out)

    def test_different_titles_with_same_slug_get_suffix(self):
        p1 = self.new("Café")
        p2 = self.new("Cafe!")
        p3 = self.new("CAFÉ?")
        self.assertEqual([p1.id, p2.id, p3.id],
                         ["2026-01-01_en_cafe", "2026-01-01_en_cafe-2", "2026-01-01_en_cafe-3"])

    def test_identical_title_same_language_same_day_refused(self):
        p = self.new("Repeat me")
        for again in ("Repeat me", "  repeat ME "):
            with self.assertRaises(FactoryError) as e:
                self.new(again)
            self.assertIn(f"already created on 2026-01-01: {p.id}", str(e.exception))
        self.new("Repeat me", created="2026-01-02")  # another day is fine

    def test_damaged_folder_with_same_id_is_never_overwritten(self):
        p = self.new("Fragile")
        (p.folder / "project.json").write_text("{")
        with self.assertRaises(FactoryError) as e:
            self.new("Fragile")
        self.assertIn("already exists but can't be read", str(e.exception))
        self.assertEqual((p.folder / "project.json").read_text(), "{")

    def test_empty_title_refused(self):
        with self.assertRaises(FactoryError):
            self.new("   ")

    def test_existing_old_style_ids_untouched(self):
        from factory.core.config import Context
        ids = sorted(p.id for p in iter_projects(Context()))
        self.assertEqual(ids, ["2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung",
                               "2026-11-17_why-octopuses-have-three-hearts"])


# ------------------------------------------------------------------ B9
class TestLanguagesDoNotCollide(Base):
    def test_same_title_in_english_and_malay_same_day(self):
        en = self.new("Nasi lemak history", lang="en", division="food-cooking")
        ms = self.new("Nasi lemak history", lang="ms", division="food-cooking")
        self.assertEqual((en.id, ms.id), ("2026-01-01_en_nasi-lemak-history", "2026-01-01_ms_nasi-lemak-history"))
        self.assertEqual(sorted(p.language for p in iter_projects(self.ctx)), ["en", "ms"])
        for lang, pid in (("en", en.id), ("ms", ms.id)):
            code, out = self.cli("status", "--lang", lang)
            self.assertIn(pid, out)

    def test_via_cli_with_ideas(self):
        self.cli("ideas", "add", "Same title", "--lang", "en", "--division", "gaming")
        self.cli("ideas", "add", "Same title", "--lang", "ms", "--division", "gaming")
        for idea_id in ("EN-006", "MS-005"):
            code, out = self.cli("new", "--idea", idea_id)
            self.assertEqual(code, 0, out)
        self.assertEqual(len(list(iter_projects(self.ctx))), 2)


# ------------------------------------------------------------------ B10
class TestUnlinkIdea(Base):
    def setUp(self):
        super().setUp()
        code, out = self.cli("new", "--idea", "EN-002")
        self.assertEqual(code, 0, out)
        self.project = next(iter_projects(self.ctx))
        self.csv = self.ctx.paths.ideas_csv("qhaze", "en")

    def row(self, idea_id):
        return next(r for r in read_csv(self.csv) if r["id"] == idea_id)

    def test_refused_while_project_exists(self):
        before = self.csv.read_bytes()
        code, out = self.cli("ideas", "unlink", "EN-002")
        self.assertEqual(code, 1)
        self.assertIn("still exists. Unlinking is only allowed after the project folder has been deleted", out)
        self.assertEqual(self.csv.read_bytes(), before)

    def test_refused_while_damaged_folder_exists(self):
        (self.project.folder / "project.json").write_text("{")
        code, out = self.cli("ideas", "unlink", "EN-002")
        self.assertEqual(code, 1)
        self.assertIn("still exists", out)

    def test_unlink_after_project_deleted(self):
        shutil.rmtree(self.project.folder)
        code, out = self.cli("ideas", "--lang", "en")
        self.assertIn(f"linked project {self.project.id} not found", out)
        self.assertIn("python -m factory ideas unlink EN-002", out)
        code, out = self.cli("new", "--idea", "EN-002")
        self.assertEqual(code, 1)
        self.assertIn("ideas unlink EN-002", out)

        other_rows = [r for r in read_csv(self.csv) if r["id"] != "EN-002"]
        code, out = self.cli("ideas", "unlink", "en-002")
        self.assertEqual(code, 0, out)
        self.assertIn(f"Unlinked EN-002 from deleted project {self.project.id}; status in_production → backlog", out)
        self.assertIn(f"set project_id back to {self.project.id}", out)
        self.assertEqual((self.row("EN-002")["status"], self.row("EN-002")["project_id"]), ("backlog", ""))
        self.assertEqual([r for r in read_csv(self.csv) if r["id"] != "EN-002"], other_rows)  # others untouched

        code, out = self.cli("new", "--idea", "EN-002")   # can be produced again
        self.assertEqual(code, 0, out)
        code, out = self.cli("ideas", "unlink", "EN-002")
        self.assertEqual(code, 1)                          # new project exists → refused again

    def test_unlink_errors(self):
        code, out = self.cli("ideas", "unlink", "EN-003")
        self.assertEqual(code, 1)
        self.assertIn("is not linked to a project", out)
        code, out = self.cli("ideas", "unlink", "EN-999")
        self.assertEqual(code, 1)
        self.assertIn("not found", out)

    def test_extra_columns_kept_on_unlink(self):
        rows = read_csv(self.csv)
        for r in rows:
            r["my_notes"] = f"note {r['id']}"
        from factory.core.files import write_csv
        write_csv(self.csv, rows, ideas.FIELDS)
        shutil.rmtree(self.project.folder)
        ideas.unlink_idea(self.ctx, "qhaze", "EN-002")
        self.assertEqual(self.row("EN-002")["my_notes"], "note EN-002")
        self.assertEqual(self.row("EN-001")["my_notes"], "note EN-001")


if __name__ == "__main__":
    unittest.main()
