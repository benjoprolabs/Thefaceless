"""Tests for M4 Script Writing Engine (v0.4.4): scaffold, versions and diff,
per-scene timing, and every Script rule in PHASE2_PLAN.md §7."""

import hashlib
import json
import unittest

from factory.core.checks import FAIL, WARN, run_checks
from factory.core.config import Context, FactoryError
from factory.core.projects import find_project
from factory.modules import scripts
from factory.modules.production import advance, create_project
from tests.helpers import add_source, make_sandbox, remove_sandbox, run_cli, tick_all
from tests.test_m3_planning import fill


def scenes(*narrations, titles=None):
    """A script body with one [SCENE] per narration (empty string = empty scene)."""
    titles = titles or [f"Scene {i}" for i in range(1, len(narrations) + 1)]
    body = "".join(f"## [SCENE {i}] {t}\n<!-- Visual: x -->\n{n}\n\n"
                   for i, (t, n) in enumerate(zip(titles, narrations), 1))
    return "# Script\n\n" + body + "## Stage checklist\n- [x] done\n"


def words(n, word="word"):
    return " ".join([word] * n)


BODY = f"{words(20, 'body')}. {words(20, 'body')}. {words(10, 'body')}."  # 50 words, sentences <= 20
GOOD_EN = ("Octopuses have three hearts.", BODY, BODY.replace("body", "more"),
           "Follow for more ocean facts.")  # 109 words ≈ 44 s: fits a 45 s target


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = self.new("Script test")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def new(self, title, lang="en", division="what-if-science", fmt="short", seconds=None):
        seconds = seconds or (45 if fmt == "short" else None)  # GOOD_EN fits a 45 s target
        return create_project(self.ctx, title, lang, division, fmt, seconds=seconds, created="2026-01-01")

    def script(self, p=None):
        return scripts.script_path(self.ctx, p or self.p)

    def write(self, *narrations, p=None):
        self.script(p).write_text(scenes(*narrations), encoding="utf-8")

    def write_plan(self, p=None, **kw):
        path = (p or self.p).folder / "02_planning/plan.md"
        path.write_text(fill(path.read_text(encoding="utf-8"), **kw), encoding="utf-8")

    def findings(self, p=None):
        return [(f.level, f.code) for f in scripts.check_script(self.ctx, p or self.p)]

    def codes(self, p=None):
        return {code for _, code in self.findings(p)}

    def set_rules(self, **values):
        path = self.tmp / "config/rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["script"].update(values)
        path.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()

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


# ------------------------------------------------------------ scaffold
class TestScaffold(Base):
    def test_one_scene_per_outline_point_rest_unchanged(self):
        self.write_plan(points=("Hook", "Three hearts", "Blue blood", "Why they crawl", "Payoff"))
        before = self.script().read_text(encoding="utf-8")
        out = self.ok("script", "scaffold", "script-test")
        self.assertIn("5 scenes", out)
        after = self.script().read_text(encoding="utf-8")
        parsed = scripts.parse_scenes(after)
        self.assertEqual([(s["number"], s["title"]) for s in parsed],
                         [(1, "Hook"), (2, "Three hearts"), (3, "Blue blood"), (4, "Why they crawl"), (5, "Payoff")])
        self.assertEqual(after.count("<!-- Visual: -->"), 5)
        # header, rules comment and checklist are kept exactly
        head = before[:before.index("## [SCENE 1]")]
        tail = before[before.index("## Stage checklist"):]
        self.assertTrue(after.startswith(head))
        self.assertTrue(after.endswith(tail))

    def test_malay_template(self):
        p = self.new("Skrip ujian", lang="ms")
        self.write_plan(p, points=("Cangkuk", "Fakta satu", "Fakta dua"))
        self.ok("script", "scaffold", p.id)
        text = self.script(p).read_text(encoding="utf-8")
        self.assertEqual([s["title"] for s in scripts.parse_scenes(text)], ["Cangkuk", "Fakta satu", "Fakta dua"])
        self.assertIn("# Skrip:", text)
        self.assertIn("Dibaca kuat sekali", text)

    def test_refuses_once_a_scene_is_written(self):
        self.write_plan()
        path = self.script()
        text = path.read_text(encoding="utf-8")
        written = text.replace("<!-- Visual: -->\n\n", "<!-- Visual: -->\nThe hook is written.\n", 1)
        path.write_text(written, encoding="utf-8")
        self.assertIn("already has written scenes", self.bad("script", "scaffold", "script-test"))
        self.assertEqual(path.read_text(encoding="utf-8"), written)  # unchanged

    def test_refuses_when_a_visual_note_is_filled(self):
        self.write_plan()
        path = self.script()
        noted = path.read_text(encoding="utf-8").replace("<!-- Visual: -->", "<!-- Visual: drone shot -->", 1)
        path.write_text(noted, encoding="utf-8")
        self.bad("script", "scaffold", "script-test")
        self.assertEqual(path.read_text(encoding="utf-8"), noted)

    def test_scaffold_twice_while_still_empty(self):
        self.write_plan(points=("A", "B", "C"))
        self.ok("script", "scaffold", "script-test")
        self.write_plan(points=("A", "B", "C", "D"))  # the outline changed; the scenes are still empty
        self.ok("script", "scaffold", "script-test")
        self.assertEqual(len(scripts.parse_scenes(self.script().read_text(encoding="utf-8"))), 4)

    def test_needs_outline_points(self):
        plan = self.p.folder / "02_planning/plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace("1. Hook", "1.").replace(
            "4. Payoff / call to action", "4."), encoding="utf-8")
        self.assertIn("no outline points", self.bad("script", "scaffold", "script-test"))
        plan.unlink()
        self.assertIn("plan.md is missing", self.bad("script", "scaffold", "script-test"))

    def test_crlf_script_keeps_its_line_endings(self):
        self.write_plan(points=("A", "B", "C"))
        path = self.script()
        crlf = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        path.write_bytes(crlf)
        self.ok("script", "scaffold", "script-test")
        data = path.read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(b"## [SCENE 3] C\r\n<!-- Visual: -->\r\n", data)
        self.assertTrue(data.endswith(crlf[crlf.index(b"## Stage checklist"):]))


# ------------------------------------------------------------ versions and diff
class TestVersions(Base):
    def test_snapshot_versions_diff(self):
        self.assertIn("No saved versions", self.ok("script", "versions", "script-test"))
        self.write(*GOOD_EN)
        self.assertIn("Saved v1", self.ok("script", "snapshot", "script-test", "--note", "first draft"))
        v1 = self.script().parent / "versions/v1.md"
        self.assertEqual(v1.read_bytes(), self.script().read_bytes())
        self.assertIn("unchanged since v1", self.bad("script", "snapshot", "script-test"))

        self.write("Octopuses have three hearts and blue blood.", *GOOD_EN[1:])
        self.ok("script", "snapshot", "script-test", "--note", "better hook")
        p = find_project(self.ctx, "script-test")
        self.assertEqual(p.meta["script_version"], 2)
        self.assertEqual([(v["version"], v["note"]) for v in p.meta["script_versions"]],
                         [(1, "first draft"), (2, "better hook")])

        out = self.ok("script", "versions", "script-test")
        self.assertIn("first draft", out)
        self.assertIn("better hook", out)
        self.assertIn("the same as v2", out)

        diff = self.ok("script", "diff", "script-test", "v1", "v2")
        self.assertIn("--- v1.md", diff)
        self.assertIn("-Octopuses have three hearts.", diff)
        self.assertIn("+Octopuses have three hearts and blue blood.", diff)
        self.assertIn("No differences", self.ok("script", "diff", "script-test", "2", "current"))
        self.write(*GOOD_EN)
        self.assertIn("+++ script.md", self.ok("script", "diff", "script-test", "v2", "current"))
        self.assertIn("changed since v2", self.ok("script", "versions", "script-test"))

    def test_unknown_version_and_existing_files_never_overwritten(self):
        self.write(*GOOD_EN)
        self.assertIn("none yet", self.bad("script", "diff", "script-test", "v1", "current"))
        folder = self.script().parent / "versions"
        folder.mkdir()
        (folder / "v3.md").write_text("kept as is", encoding="utf-8")
        self.assertIn("Saved v4", self.ok("script", "snapshot", "script-test"))
        self.assertEqual((folder / "v3.md").read_text(encoding="utf-8"), "kept as is")
        self.assertIn("Unknown version 'v9'", self.bad("script", "diff", "script-test", "v9", "v3"))
        self.assertIn("Unknown version", self.bad("script", "diff", "script-test", "latest", "v3"))

    def test_snapshot_keeps_bytes_exactly(self):
        raw = scenes(*GOOD_EN).replace("\n", "\r\n").encode("utf-8")
        self.script().write_bytes(raw)
        number, path = scripts.snapshot(self.ctx, self.p)
        self.assertEqual(path.read_bytes(), raw)


# ------------------------------------------------------------ timing
class TestTiming(Base):
    def test_per_scene_timing(self):
        self.write(words(15), words(30), "")
        r = scripts.analyse(self.ctx, self.p)
        self.assertEqual([(t["number"], t["words"], t["seconds"], t["start"], t["end"]) for t in r["timing"]],
                         [(1, 15, 6.0, 0.0, 6.0), (2, 30, 12.0, 6.0, 18.0), (3, 0, 0.0, 18.0, 18.0)])
        out = self.bad("script", "check", "script-test")  # scene 3 is empty
        self.assertIn("150 words per minute", out)
        self.assertIn("[SCENE 2]   6.0– 18.0 s", out)

    def test_malay_uses_the_malay_rate(self):
        ms = self.new("Ujian masa", lang="ms")
        for p in (self.p, ms):
            self.write(words(70), words(70), p=p)
        en_t = scripts.analyse(self.ctx, self.p)["timing"]
        ms_t = scripts.analyse(self.ctx, ms)["timing"]
        self.assertEqual(en_t[-1]["end"], 56.0)   # 140 words at 150 wpm
        self.assertEqual(ms_t[-1]["end"], 60.0)   # 140 words at 140 wpm
        self.assertEqual(scripts.analyse(self.ctx, ms)["words_per_minute"], 140)
        self.assertIn("140 words per minute", self.cli("script", "check", ms.id)[1])


# ------------------------------------------------------------ Script rules (plan §7)
class TestRules(Base):
    def test_good_script_has_no_findings(self):
        self.write(*GOOD_EN)
        self.assertEqual(self.findings(), [])

    def test_length_outside_format_fails_and_off_target_warns(self):
        self.write("Too short.")
        self.assertIn((FAIL, "SCRIPT_LENGTH"), self.findings())
        self.write(words(10) + ".", words(20) + ".", words(20) + ".", "Follow us.")  # ~21 s vs 45 s target
        self.assertIn((WARN, "SCRIPT_TARGET"), self.findings())
        self.assertNotIn((FAIL, "SCRIPT_LENGTH"), self.findings())

    def test_empty_scene_and_no_scenes_fail(self):
        self.write(*GOOD_EN[:2], "", GOOD_EN[3])
        self.assertIn((FAIL, "SCRIPT_EMPTY_SCENE"), self.findings())
        self.script().write_text("# Script\n\nNo scenes here.\n", encoding="utf-8")
        self.assertIn((FAIL, "SCRIPT_NO_SCENES"), self.findings())

    def test_hook_length_short_and_long(self):
        self.write(words(13) + ".", *GOOD_EN[1:])  # 13 words = 5.2 s > 5 s
        self.assertIn((WARN, "SCRIPT_HOOK"), self.findings())
        self.write(words(12) + ".", *GOOD_EN[1:])  # 4.8 s
        self.assertNotIn("SCRIPT_HOOK", self.codes())
        long = self.new("Long script", fmt="long", seconds=300)
        body = [words(20) + "."] * 40
        self.write(words(50) + ".", *body, "Subscribe for more.", p=long)  # 20 s exactly: OK
        self.assertNotIn("SCRIPT_HOOK", self.codes(long))
        self.write(words(51) + ".", *body, "Subscribe for more.", p=long)
        self.assertIn((WARN, "SCRIPT_HOOK"), self.findings(long))

    def test_sentence_over_25_words(self):
        self.write(GOOD_EN[0], words(25) + ". " + words(26, "long") + ".", GOOD_EN[2], GOOD_EN[3])
        found = [f for f in scripts.check_script(self.ctx, self.p) if f.code == "SCRIPT_SENTENCE"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].level, WARN)
        self.assertIn("scene 2: a sentence has 26 words", found[0].message)

    def test_call_to_action_in_last_scene(self):
        self.write(*GOOD_EN[:3], "That is all.")
        self.assertIn((WARN, "SCRIPT_CTA"), self.findings())
        self.write(*GOOD_EN[:3], "Let me know in the comments.")
        self.assertNotIn("SCRIPT_CTA", self.codes())
        self.write("Follow for more.", *GOOD_EN[1:3], "That is all.")  # must be in the LAST scene
        self.assertIn("SCRIPT_CTA", self.codes())

    def test_malay_call_to_action(self):
        ms = self.new("Ujian CTA", lang="ms")
        self.write(words(20, "kata") + ".", words(20, "isi") + ".", "Itu sahaja.", p=ms)
        self.assertIn((WARN, "SCRIPT_CTA"), self.findings(ms))
        self.write(words(20, "kata") + ".", words(20, "isi") + ".", "Langgan untuk fakta lain.", p=ms)
        self.assertNotIn("SCRIPT_CTA", self.codes(ms))

    def test_product_affiliate_disclosure(self):
        p = self.new("Best headphones", division="product-affiliate")
        self.write(*GOOD_EN, p=p)
        self.assertIn((FAIL, "SCRIPT_DISCLOSURE"), self.findings(p))
        self.write(GOOD_EN[0], GOOD_EN[1], GOOD_EN[2],
                   "I earn a commission if you buy through my link. Follow for more.", p=p)
        self.assertNotIn("SCRIPT_DISCLOSURE", self.codes(p))
        # only spoken narration counts, not comments
        text = scenes(*GOOD_EN).replace("<!-- Visual: x -->", "<!-- affiliate commission -->")
        self.script(p).write_text(text, encoding="utf-8")
        self.assertIn("SCRIPT_DISCLOSURE", self.codes(p))
        # other divisions don't need it
        self.write(*GOOD_EN)
        self.assertNotIn("SCRIPT_DISCLOSURE", self.codes())

    def test_malay_disclosure(self):
        p = self.new("Fon kepala terbaik", lang="ms", division="product-affiliate")
        self.write(words(20, "kata") + ".", "Langgan sekarang.", p=p)
        self.assertIn("SCRIPT_DISCLOSURE", self.codes(p))
        self.write("Video ini mengandungi pautan afiliasi. " + words(20, "kata") + ".", "Langgan sekarang.", p=p)
        self.assertNotIn("SCRIPT_DISCLOSURE", self.codes(p))

    def test_psychology_sensitive_terms(self):
        p = self.new("Overthinking", division="psychology")
        self.write("This habit will cure your anxiety.", *GOOD_EN[1:], p=p)
        found = [f for f in scripts.check_script(self.ctx, p) if f.code == "SCRIPT_SENSITIVE"]
        self.assertEqual([f.level for f in found], [WARN])
        self.assertIn("'cure'", found[0].message)
        self.assertIn("No medical or diagnostic advice", found[0].message)
        self.write("Curious minds notice more.", *GOOD_EN[1:], p=p)  # whole words only
        self.assertNotIn("SCRIPT_SENSITIVE", self.codes(p))
        self.write("Doctors DIAGNOSE this.", *GOOD_EN[1:])  # other divisions: not checked
        self.assertNotIn("SCRIPT_SENSITIVE", self.codes())
        ms = self.new("Fikir berlebihan", lang="ms", division="psychology")
        self.write("Tabiat ini boleh menyembuhkan kebimbangan.", "Langgan sekarang.", p=ms)
        self.assertIn("SCRIPT_SENSITIVE", self.codes(ms))

    def test_thresholds_and_phrases_from_rules_json(self):
        self.write(words(13) + ".", *GOOD_EN[1:])
        self.set_rules(hook_max_seconds={"short": 6})
        self.assertNotIn("SCRIPT_HOOK", self.codes())
        self.set_rules(max_sentence_words=15)
        self.assertIn("SCRIPT_SENTENCE", self.codes())
        self.set_rules(cta_phrases={"en": ["ocean facts"]})
        self.write(*GOOD_EN[:3], "Thanks for watching.")
        self.assertIn("SCRIPT_CTA", self.codes())
        self.write(*GOOD_EN)
        self.assertNotIn("SCRIPT_CTA", self.codes())

    def test_broken_rule_values(self):
        self.write(*GOOD_EN)
        self.set_rules(max_sentence_words="many")
        with self.assertRaises(FactoryError) as e:
            scripts.check_script(self.ctx, self.p)
        self.assertIn("script.max_sentence_words", str(e.exception))
        self.set_rules(max_sentence_words=25, cta_phrases=["follow"])
        self.assertIn("script.cta_phrases", self.bad("script", "check", "script-test"))
        self.set_rules(cta_phrases={}, hook_max_seconds=5)
        self.assertIn("script.hook_max_seconds", self.bad("script", "check", "script-test"))

    def test_missing_new_keys_use_defaults(self):
        path = self.tmp / "config/rules.json"
        path.write_text(json.dumps({"script": {"target_tolerance_percent": 20}}), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.write(words(13) + ".", *GOOD_EN[1:])
        self.assertIn("SCRIPT_HOOK", self.codes())   # default 5 s
        self.assertNotIn("SCRIPT_CTA", self.codes())  # no phrases configured: not checked


# ------------------------------------------------------------ gate and CLI
class TestGate(Base):
    def to_script(self, p):
        tick_all(p.folder / "01_research/research.md")
        add_source(self.ctx, p)
        advance(self.ctx, p)
        self.write_plan(p)
        tick_all(p.folder / "02_planning/plan.md")
        advance(self.ctx, p)

    def test_disclosure_blocks_the_script_gate(self):
        p = self.new("Gate headphones", division="product-affiliate")
        self.to_script(p)
        self.write(*GOOD_EN, p=p)
        tick_all(self.script(p))
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, p)
        self.assertIn("SCRIPT_DISCLOSURE", str(e.exception))
        self.assertIn("SCRIPT_DISCLOSURE", self.bad("script", "check", p.id))
        self.write(GOOD_EN[0], "This video is sponsored. " + GOOD_EN[1], *GOOD_EN[2:], p=p)
        tick_all(self.script(p))
        self.assertEqual(advance(self.ctx, p), "factcheck")

    def test_warnings_do_not_block(self):
        self.to_script(self.p)
        self.write(words(13) + ".", *GOOD_EN[1:3], "That is all.")
        tick_all(self.script())
        codes = {f.code for f in run_checks(self.ctx, self.p)}
        self.assertTrue({"SCRIPT_HOOK", "SCRIPT_CTA"} <= codes)
        self.assertEqual(advance(self.ctx, self.p), "factcheck")

    def test_full_scaffold_workflow_with_commands(self):
        self.to_script(self.p)
        self.ok("script", "scaffold", "script-test")
        path = self.script()
        text = path.read_text(encoding="utf-8")
        for narration in GOOD_EN:
            text = text.replace("<!-- Visual: -->\n\n", f"<!-- Visual: -->\n{narration}\n", 1)
        path.write_text(text, encoding="utf-8")
        self.ok("script", "snapshot", "script-test", "--note", "draft")
        out = self.ok("script", "check", "script-test")
        self.assertIn("Scenes: 4", out)
        tick_all(path)
        self.ok("advance", "script-test")


class TestSamplesUnchanged(unittest.TestCase):
    def test_sample_scripts_checked_without_changes(self):
        ctx = Context()
        octopus = find_project(ctx, "octopus")
        path = scripts.script_path(ctx, octopus)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        # The English sample's hook is 13 words (5.2 s): only a WARN, nothing blocks.
        self.assertEqual([(f.level, f.code) for f in scripts.check_script(ctx, octopus)], [(WARN, "SCRIPT_HOOK")])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertNotIn("script_version", octopus.meta)
        self.assertFalse((path.parent / "versions").exists())


if __name__ == "__main__":
    unittest.main()
