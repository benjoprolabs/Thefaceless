"""Tests for M6 Shot List Generator (v0.4.6): merging generator (filled-in
fields kept, new scenes added, times refreshed, removed scenes flagged),
asset links, every Shot list rule in PHASE2_PLAN.md §7 and the Visuals gate.
Approved decisions 1A-6A."""

import hashlib
import json
import unittest

from factory.core.checks import FAIL, WARN, failures, run_checks
from factory.core.config import Context, FactoryError
from factory.core.files import read_csv, read_csv_table, write_csv
from factory.core.projects import find_project
from factory.modules import assets, shots
from factory.modules.production import advance, create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli, tick_all


def script(*scenes):
    """A script with one [SCENE] per (title, words) pair; 150 wpm → words / 2.5 seconds."""
    body = "".join(f"## [SCENE {i}] {title}\n{' '.join(['word'] * words)}.\n\n"
                   for i, (title, words) in enumerate(scenes, 1))
    return "# Script\n\n" + body + "## Stage checklist\n- [x] done\n"


FOUR = (("Hook", 10), ("Setup", 10), ("Main", 10), ("End", 10))  # 4 s each


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = self.new("Shot test")
        self.set_script(*FOUR)

    def tearDown(self):
        remove_sandbox(self.tmp)

    def new(self, title, lang="en", fmt="short", seconds=None):
        return create_project(self.ctx, title, lang, "what-if-science", fmt, seconds=seconds, created="2026-01-01")

    def set_script(self, *scenes, p=None):
        (p or self.p).folder.joinpath("03_script/script.md").write_text(script(*scenes), encoding="utf-8")

    def path(self, p=None):
        return shots.shotlist_path(self.ctx, p or self.p)

    def rows(self, p=None):
        return read_csv(self.path(p))

    def save(self, rows, p=None):
        header, _ = read_csv_table(self.path(p))
        write_csv(self.path(p), rows, header or list(rows[0]))

    def edit(self, scene, p=None, **values):
        rows = self.rows(p)
        for r in rows:
            if r["scene"] == str(scene):
                r.update(values)
        self.save(rows, p)

    def all_done(self, p=None):
        self.save([{**r, "status": "done"} for r in self.rows(p)], p)

    def asset(self, name="clip.mp4", license="CC0", source="Pexels"):
        src = self.tmp / name
        src.write_bytes(b"x")
        return assets.add_asset(self.ctx, src, "broll", source=source, license=license)

    def findings(self, p=None):
        return [(f.level, f.code) for f in shots.check_shots(self.ctx, p or self.p)]

    def codes(self, p=None):
        return {code for _, code in self.findings(p)}

    def cli(self, *argv):
        self.ctx.warnings.clear()
        return run_cli(list(argv), self.ctx)

    def ok(self, *argv):
        code, out = self.cli(*argv)
        self.assertEqual(code, 0, f"{argv}\n{out}")
        return out

    def bad(self, *argv):
        code, out = self.cli(*argv)
        self.assertEqual(code, 1, f"{argv}\n{out}")
        return out


# ------------------------------------------------------------ generate (merge)
class TestGenerate(Base):
    def test_first_run_replaces_the_template_row(self):
        self.ok("shots", "generate", "shot-test")
        rows = self.rows()
        self.assertEqual([(r["scene"], r["start_sec"], r["end_sec"], r["narration_summary"], r["status"])
                          for r in rows],
                         [("1", "0", "4", "Hook", "todo"), ("2", "4", "8", "Setup", "todo"),
                          ("3", "8", "12", "Main", "todo"), ("4", "12", "16", "End", "todo")])
        self.assertIn("asset_id", read_csv_table(self.path())[0])

    def test_regenerating_keeps_every_filled_in_field(self):
        self.ok("shots", "generate", "shot-test")
        filled = {"visual_type": "animation", "visual_description": "Diagram, with a comma",
                  "source": "Pexels", "license": "Pexels License", "file": "broll/a.mp4",
                  "status": "done", "asset_id": "AS0009", "narration_summary": "My own summary"}
        self.edit(2, **filled)
        rows = self.rows()
        rows[0]["my_notes"] = "extra column"  # added in Excel
        self.save(rows)
        self.set_script(("Hook", 10), ("Setup", 20), ("Main", 10), ("End", 10))  # scene 2 gets longer
        out = self.ok("shots", "generate", "shot-test")
        self.assertIn("times refreshed", out)
        row = {r["scene"]: r for r in self.rows()}["2"]
        for key, value in filled.items():
            self.assertEqual(row[key], value, key)
        self.assertEqual((row["start_sec"], row["end_sec"]), ("4", "12"))  # timings refreshed
        self.assertEqual(self.rows()[0]["my_notes"], "extra column")
        before = self.path().read_bytes()
        self.assertIn("Nothing changed", self.ok("shots", "generate", "shot-test"))
        self.assertEqual(self.path().read_bytes(), before)  # second run changes nothing

    def test_new_scenes_added_and_removed_scenes_flagged_not_deleted(self):
        self.ok("shots", "generate", "shot-test")
        self.edit(4, visual_description="Logo", status="done", file="x.mp4")
        self.set_script(("Hook", 10), ("Setup", 10), ("Main", 10))  # scene 4 removed
        out = self.ok("shots", "generate", "shot-test")
        self.assertIn("marked 'removed'", out)
        row4 = {r["scene"]: r for r in self.rows()}["4"]
        self.assertEqual((row4["status"], row4["visual_description"], row4["file"]), ("removed", "Logo", "x.mp4"))
        self.set_script(*FOUR, ("Outro", 5))  # scene 4 back, scene 5 new
        out = self.ok("shots", "generate", "shot-test")
        self.assertIn("scene 5: added", out)
        self.assertIn("back in the script", out)
        rows = {r["scene"]: r for r in self.rows()}
        self.assertEqual((rows["4"]["status"], rows["4"]["visual_description"]), ("todo", "Logo"))
        self.assertEqual((rows["5"]["start_sec"], rows["5"]["end_sec"], rows["5"]["status"]), ("16", "18", "todo"))

    def test_scene_split_into_several_shots_keeps_its_times(self):
        self.ok("shots", "generate", "shot-test")
        rows = self.rows()
        rows[1:2] = [{**rows[1], "end_sec": "6", "visual_description": "A"},
                     {**rows[1], "start_sec": "6", "visual_description": "B"}]
        self.save(rows)
        self.set_script(("Hook", 10), ("Setup", 15), ("Main", 10), ("End", 10))
        self.ok("shots", "generate", "shot-test")
        scene2 = [r for r in self.rows() if r["scene"] == "2"]
        self.assertEqual([(r["start_sec"], r["end_sec"], r["visual_description"]) for r in scene2],
                         [("4", "6", "A"), ("6", "8", "B")])
        self.assertEqual({r["scene"]: r for r in self.rows()}["3"]["start_sec"], "10")

    def test_old_file_without_asset_id_and_excel_file(self):
        self.path().write_bytes("scene;start_sec;end_sec;narration_summary;visual_type;visual_description;"
                                "source;license;file;status\r\n1;0;4;Hook;photo;Café scene;own;;;done\r\n"
                                .encode("cp1252"))
        self.ok("shots", "generate", "shot-test")
        header, rows = read_csv_table(self.path())
        self.assertIn("asset_id", header)
        self.assertEqual((rows[0]["visual_description"], rows[0]["status"]), ("Café scene", "done"))
        self.assertEqual(len(rows), 4)

    def test_force_rebuilds_and_script_shotlist_is_the_same_command(self):
        self.ok("script", "shotlist", "shot-test")
        self.edit(1, visual_description="kept")
        self.assertIn("Nothing changed", self.ok("script", "shotlist", "shot-test"))
        self.assertEqual(self.rows()[0]["visual_description"], "kept")
        self.ok("shots", "generate", "shot-test", "--force")
        self.assertEqual(self.rows()[0]["visual_description"], "")

    def test_malay_project_uses_the_malay_rate(self):
        ms = self.new("Ujian syot", lang="ms")
        self.set_script(("Cangkuk", 14), ("Isi", 14), p=ms)  # 14 words at 140 wpm = 6 s
        self.ok("shots", "generate", ms.id)
        self.assertEqual([(r["start_sec"], r["end_sec"]) for r in self.rows(ms)], [("0", "6"), ("6", "12")])


# ------------------------------------------------------------ link
class TestLink(Base):
    def setUp(self):
        super().setUp()
        self.ok("shots", "generate", "shot-test")

    def test_link_sets_asset_and_fills_only_an_empty_file(self):
        a = self.asset()
        out = self.ok("shots", "link", "shot-test", "1", "--asset", a["id"].lower())
        self.assertIn("file filled in", out)
        row = self.rows()[0]
        self.assertEqual((row["asset_id"], row["file"]), (a["id"], "broll/clip.mp4"))
        self.edit(2, file="my/own.mp4")
        self.ok("shots", "link", "shot-test", "2", "--asset", a["id"])
        self.assertEqual(self.rows()[1]["file"], "my/own.mp4")  # never overwritten
        self.assertEqual(self.rows()[1]["source"], "")  # licence is read from the register, not copied

    def test_refusals(self):
        a = self.asset()
        b = self.asset("other.mp4")
        self.assertIn("not in assets/register.csv", self.bad("shots", "link", "shot-test", "1", "--asset", "AS0099"))
        self.assertIn("Scene 9 has no row", self.bad("shots", "link", "shot-test", "9", "--asset", a["id"]))
        self.assertIn("must be a number", self.bad("shots", "link", "shot-test", "x", "--asset", a["id"]))
        self.ok("shots", "link", "shot-test", "1", "--asset", a["id"])
        self.ok("shots", "link", "shot-test", "1", "--asset", a["id"])  # same asset again is fine
        before = self.path().read_bytes()
        self.assertIn("already linked to AS0001", self.bad("shots", "link", "shot-test", "1", "--asset", b["id"]))
        self.assertEqual(self.path().read_bytes(), before)


# ------------------------------------------------------------ rules (plan §7)
class TestRules(Base):
    def setUp(self):
        super().setUp()
        self.ok("shots", "generate", "shot-test")
        self.all_done()

    def test_complete_list_passes(self):
        self.assertEqual(self.findings(), [])
        self.assertIn("Shot list OK", self.ok("shots", "check", "shot-test"))

    def test_scene_without_a_row_fails(self):
        self.save([r for r in self.rows() if r["scene"] != "3"])
        self.assertIn((FAIL, "SHOT_MISSING_SCENE"), self.findings())
        self.edit(2, status="removed")  # a removed row doesn't count as coverage
        found = self.findings()
        self.assertEqual(found.count((FAIL, "SHOT_MISSING_SCENE")), 2)
        self.assertIn((WARN, "SHOT_REMOVED"), found)

    def test_rows_not_done_fail(self):
        self.edit(2, status="todo")
        self.edit(3, status="in_progress")
        found = [f for f in shots.check_shots(self.ctx, self.p) if f.code == "SHOT_NOT_DONE"]
        self.assertEqual([f.level for f in found], [FAIL])
        self.assertIn("scene 2, 3", found[0].message)

    def test_external_source_needs_a_licence(self):
        self.edit(1, source="Pexels")
        self.assertEqual(self.findings(), [(FAIL, "SHOT_NO_LICENSE")])
        self.edit(1, license="Pexels License")
        self.assertEqual(self.findings(), [])
        for own in ("self-made", "Own", "original", ""):
            self.edit(2, source=own, license="")
            self.assertNotIn("SHOT_NO_LICENSE", self.codes(), own)

    def test_licence_taken_from_the_register_when_linked(self):
        good, unlicensed = self.asset("a.mp4", license="CC0"), self.asset("b.mp4", license="")
        self.ok("shots", "link", "shot-test", "1", "--asset", good["id"])
        self.ok("shots", "link", "shot-test", "2", "--asset", unlicensed["id"])
        found = [f for f in shots.check_shots(self.ctx, self.p) if f.code == "SHOT_NO_LICENSE"]
        self.assertEqual(len(found), 1)
        self.assertIn("scene 2", found[0].message)
        self.assertIn(f"linked asset {unlicensed['id']} has none either", found[0].message)
        self.edit(2, license="CC-BY 4.0")  # a licence in the row also counts
        self.assertNotIn("SHOT_NO_LICENSE", self.codes())

    def test_unknown_asset_fails(self):
        self.edit(3, asset_id="AS0042")
        self.assertIn((FAIL, "SHOT_UNKNOWN_ASSET"), self.findings())

    def test_gaps_and_overlaps_warn(self):
        self.edit(2, start_sec="5")
        self.assertIn((WARN, "SHOT_GAP"), self.findings())
        self.edit(2, start_sec="3")
        self.assertIn((WARN, "SHOT_OVERLAP"), self.findings())
        self.edit(2, start_sec="x")
        self.assertIn((WARN, "SHOT_TIME"), self.findings())

    def test_short_form_shot_longer_than_the_limit(self):
        self.edit(4, end_sec="18")  # 6 s
        self.assertIn((WARN, "SHOT_TOO_LONG"), self.findings())
        long = self.new("Long video", fmt="long", seconds=300)
        self.set_script(("A", 400), ("B", 350), p=long)
        self.ok("shots", "generate", long.id)
        self.all_done(long)
        self.assertNotIn("SHOT_TOO_LONG", self.codes(long))  # the limit is for short-form only

    def test_linked_file_missing_locally_warns(self):
        self.edit(1, file="broll/missing.mp4")
        self.assertEqual(self.findings(), [(WARN, "SHOT_FILE_MISSING")])
        a = self.asset("here.mp4")
        self.edit(1, file=a["file"])  # found in assets/
        (self.p.folder / "06_visuals/own.png").write_bytes(b"x")
        self.edit(2, file="06_visuals/own.png")  # found in the project folder
        self.assertEqual(self.findings(), [])

    def test_row_for_a_scene_not_in_the_script_warns(self):
        rows = self.rows()
        self.save(rows + [{**rows[0], "scene": "9"}])
        self.assertIn((WARN, "SHOT_UNKNOWN_SCENE"), self.findings())

    def test_settings_from_rules_json(self):
        path = self.tmp / "config/rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["shots"] = {"max_shot_seconds": {"short": 3}, "self_made_sources": ["home-made"]}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.edit(1, source="home-made")
        self.edit(2, source="own")
        codes = self.findings()
        self.assertIn((WARN, "SHOT_TOO_LONG"), codes)
        self.assertEqual(codes.count((FAIL, "SHOT_NO_LICENSE")), 1)  # 'own' is no longer self-made
        data["shots"] = {"max_shot_seconds": {"short": "five"}}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.assertIn("shots.max_shot_seconds.short", self.bad("shots", "check", "shot-test"))

    def test_missing_or_broken_file(self):
        self.path().write_text("title,notes\nx,y\n", encoding="utf-8")
        self.assertEqual(self.findings(), [(FAIL, "SHOTS_FILE")])
        self.path().unlink()
        self.assertEqual(self.findings(), [(FAIL, "SHOTS_MISSING")])

    def test_project_past_visuals_gets_warnings(self):
        self.edit(1, status="todo")
        self.p.meta["stage"] = "edit"
        self.p.save()
        found = shots.check_shots(self.ctx, self.p)
        self.assertEqual([(f.level, f.code) for f in found], [(WARN, "SHOT_NOT_DONE")])
        self.assertIn("already past Visuals", found[0].message)


# ------------------------------------------------------------ gate
class TestGate(Base):
    def setUp(self):
        super().setUp()
        self.p.meta["stage"] = "visuals"
        self.p.save()
        self.ok("shots", "generate", "shot-test")
        self.visuals = self.p.folder / "06_visuals/visuals.md"

    def blocked_by(self, code):
        tick_all(self.visuals)
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        self.assertIn(code, str(e.exception))

    def test_each_fail_blocks_and_a_complete_list_advances(self):
        self.blocked_by("SHOT_NOT_DONE")
        self.all_done()
        self.edit(1, source="Pexels")
        self.blocked_by("SHOT_NO_LICENSE")
        self.edit(1, source="own", asset_id="AS0077")
        self.blocked_by("SHOT_UNKNOWN_ASSET")
        self.edit(1, asset_id="")
        self.save([r for r in self.rows() if r["scene"] != "2"])
        self.blocked_by("SHOT_MISSING_SCENE")
        self.ok("shots", "generate", "shot-test")
        self.edit(2, status="done")
        self.assertEqual(failures(run_checks(self.ctx, self.p)), [])
        self.assertEqual(advance(self.ctx, self.p), "edit")

    def test_force_is_recorded(self):
        tick_all(self.visuals)
        advance(self.ctx, self.p, force=True)
        self.assertIn("SHOT_NOT_DONE", self.p.meta["history"][-1]["forced_findings"])


class TestSamplesUnchanged(unittest.TestCase):
    def test_english_sample_has_no_fail_and_is_not_changed(self):
        ctx = Context()
        octopus = find_project(ctx, "octopus")
        path = shots.shotlist_path(ctx, octopus)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        found = shots.check_shots(ctx, octopus)
        self.assertEqual({f.level for f in found}, {WARN})
        self.assertEqual({f.code for f in found}, {"SHOT_TOO_LONG", "SHOT_FILE_MISSING"})
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
