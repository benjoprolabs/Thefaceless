"""End-to-end: the whole 10-stage workflow driven only through CLI commands."""

import unittest

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
            "show", "advance", "check", "back", "migrate", "publish", "analytics", "assets", "research"]))

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
        tick_all(p.folder / "02_planning/plan.md")
        self.ok("advance", pid)

        # 3 Script → 4 Fact check
        (p.folder / "03_script/script.md").write_text(SCRIPT, encoding="utf-8")
        self.assertIn("Claims missing", self.bad("script", "check", pid))
        self.ok("advance", pid)
        fc = p.folder / "04_factcheck/factcheck.md"
        fc.write_text(fc.read_text(encoding="utf-8").replace("| F1  |                              |",
                                             "| F1  | brain notices |\n| F2  | twice as many |"), encoding="utf-8")
        tick_all(fc)
        self.assertIn("OK", self.ok("script", "check", pid))
        self.ok("advance", pid)

        # 5 Voice-over: produced externally, manual checklist only
        self.assertIn("spotlight effect", self.ok("script", "text", pid))
        tick_all(p.folder / "05_voice/voice.md")
        self.ok("advance", pid)

        # 6 Visuals → 7 Edit → 8 QC → 9 Publish
        self.ok("script", "shotlist", pid)
        self.bad("script", "shotlist", pid)  # refuses to overwrite
        for stage_file in ("06_visuals/visuals.md", "07_edit/edit.md", "08_qc/qc.md"):
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
