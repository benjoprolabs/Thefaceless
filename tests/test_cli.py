"""End-to-end: the whole 10-stage workflow driven only through CLI commands."""

import unittest

from factory.core.files import read_csv, write_csv
from factory.core.projects import find_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli, tick_all

SCRIPT = """# Script
## [SCENE 1] Hook
Did you know your brain notices you far more than anyone else does [F1]?
## [SCENE 2] Point
Psychologists call this the spotlight effect. We think everyone sees our mistakes.
In studies, people guessed twice as many others noticed them as really did [F2].
## [SCENE 3] Payoff
So relax. Nobody is watching that closely. Follow for more psychology in a minute.
## Stage checklist
- [x] ok
"""


class TestCLIWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()

    def tearDown(self):
        remove_sandbox(self.tmp)

    def ok(self, *argv):
        code, out = run_cli(list(argv), self.ctx)
        self.assertEqual(code, 0, f"{argv}\n{out}")
        return out

    def bad(self, *argv):
        code, out = run_cli(list(argv), self.ctx)
        self.assertEqual(code, 1, f"{argv}\n{out}")
        return out

    def test_read_only_commands(self):
        for argv in (["dashboard"], ["niches"], ["niches", "show", "gaming"], ["ideas"],
                     ["ideas", "--lang", "ms"], ["status"],
                     ["library", "visuals", "--division", "gaming"], ["publish"], ["assets"],
                     ["assets", "check"], ["analytics", "report"], []):
            self.ok(*argv)

    def test_voice_commands_removed(self):
        from factory.cli import build_parser
        commands = build_parser()._subparsers._group_actions[0].choices
        self.assertNotIn("voice", commands)
        self.assertEqual(sorted(commands), sorted([
            "dashboard", "niches", "ideas", "script", "library", "new", "status",
            "show", "advance", "check", "back", "migrate", "publish", "analytics", "assets", "research", "plan",
            "factcheck", "shots"]))

    def test_errors_are_friendly(self):
        self.assertIn("not found", self.bad("new", "--idea", "EN-999"))
        self.assertIn("No project matches", self.bad("show", "nothing"))
        self.assertIn("Unknown division", self.bad("ideas", "add", "x", "--lang", "en", "--division", "cars"))

    def test_full_workflow(self):
        self.ok("ideas", "add", "The spotlight effect", "--lang", "en", "--division", "psychology",
                "--demand", "4", "--competition", "3", "--effort", "1")
        self.ok("new", "--idea", "EN-006", "--seconds", "30")
        pid = "spotlight-effect"
        p = find_project(self.ctx, pid)

        # 1 Research → 2 Planning
        self.assertIn("checklist not complete", self.bad("advance", pid))
        tick_all(p.folder / "01_research/research.md")
        self.assertIn("SOURCES_EMPTY", self.bad("advance", pid))  # M2 gate: new projects start with an empty sources.csv
        self.ok("research", "add-source", pid, "--title", "Spotlight effect study", "--type", "study",
                "--url", "https://psycnet.apa.org/record/2000-02655-002", "--accessed", "today")
        self.ok("advance", pid)
        plan = p.folder / "02_planning/plan.md"
        tick_all(plan)
        self.assertIn("PLAN_HOOK", self.bad("advance", pid))  # M3 gate: the plan must be filled in
        text = plan.read_text(encoding="utf-8")
        text = text.replace("## Angle / hook\n", "## Angle / hook\nNobody notices you as much as you think.\n")
        text = text.replace("2.\n3.\n", "2. What the studies found\n3. Why it happens\n")
        text = text.replace("- **Primary keyword:**", "- **Primary keyword:** spotlight effect")
        plan.write_text(text, encoding="utf-8")
        self.ok("plan", "set-date", pid, "2026-12-01")
        self.ok("advance", pid)

        # 3 Script → 4 Fact check
        (p.folder / "03_script/script.md").write_text(SCRIPT, encoding="utf-8")
        self.assertIn("Claims missing", self.bad("script", "check", pid))
        self.ok("advance", pid)
        fc = p.folder / "04_factcheck/factcheck.md"
        out = self.ok("factcheck", "sync", pid)  # M5: rows pre-filled from the script
        self.assertIn("Filled blank row(s): F1", out)  # the template's empty F1 row
        self.assertIn("Added row(s): F2", out)
        tick_all(fc)
        self.assertIn("FACTCHECK_NO_VERDICT", self.bad("advance", pid))  # M5 gate: verdicts and sources
        text = fc.read_text(encoding="utf-8")
        for ref in ("F1", "F2"):
            text = "\n".join(line.replace(" | | | |", " | S1 | ✅ | |") if line.startswith(f"| {ref} ") else line
                             for line in text.split("\n"))
        fc.write_text(text, encoding="utf-8")
        self.assertIn("FACTCHECK_WEAK_SOURCES", self.bad("factcheck", "check", pid))  # S1 still unverified
        self.ok("research", "verify", pid, "S1", "verified")
        self.assertIn("Fact check OK", self.ok("factcheck", "check", pid))
        self.assertIn("OK", self.ok("script", "check", pid))
        self.ok("advance", pid)

        # 5 Voice-over: produced externally, manual checklist only
        self.assertIn("spotlight effect", self.ok("script", "text", pid))
        tick_all(p.folder / "05_voice/voice.md")
        self.ok("advance", pid)

        # 6 Visuals → 7 Edit → 8 QC → 9 Publish
        self.ok("script", "shotlist", pid)
        shot = p.folder / "06_visuals/shotlist.csv"
        rows = read_csv(shot)
        rows[0]["visual_description"] = "Crowd looking at a stage"  # filled in by hand
        write_csv(shot, rows, list(rows[0]))
        self.assertIn("Nothing changed", self.ok("script", "shotlist", pid))  # M6: merges, never overwrites
        self.assertEqual(read_csv(shot)[0]["visual_description"], "Crowd looking at a stage")
        tick_all(p.folder / "06_visuals/visuals.md")
        self.assertIn("SHOT_NOT_DONE", self.bad("advance", pid))  # M6 gate: every row 'done'
        write_csv(shot, [{**r, "status": "done"} for r in read_csv(shot)], list(rows[0]))
        self.ok("shots", "check", pid)  # no FAIL (warnings only)
        self.ok("advance", pid)
        for stage_file in ("07_edit/edit.md", "08_qc/qc.md"):
            tick_all(p.folder / stage_file)
            self.ok("advance", pid)
        self.ok("publish", "record", pid, "--platform", "youtube_shorts", "--url", "https://youtube.com/shorts/abc123")
        tick_all(p.folder / "09_publish/publish.md")
        self.ok("advance", pid)

        # 10 Analytics
        self.ok("analytics", "add", pid, "--platform", "youtube_shorts", "--views", "1500", "--likes", "90")
        self.assertIn("1500", self.ok("analytics", "report"))
        self.assertIn("already at the last stage", self.bad("advance", pid))
        show = self.ok("show", pid)
        self.assertEqual(show.count("✔"), 9)
        self.assertIn("10/10", self.ok("status"))


if __name__ == "__main__":
    unittest.main()
