"""Tests for M0 Foundations (v0.4.0).

- checks framework and stage gates that use it
- `check` and `back` commands
- config/rules.json
- project format versions (schema_version) and `migrate`
- cross-platform behaviour: path display, output encoding, file encodings
- free GitHub Actions CI configuration
"""

import ast
import hashlib
import io
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from factory.cli import main
from factory.core import checks, migrate
from factory.core.checks import FAIL, INFO, WARN, Finding, failures, format_finding, run_checks
from factory.core.config import ROOT, FactoryError
from factory.core.errors import display_path
from factory.core.projects import CURRENT_SCHEMA, find_project, iter_projects
from factory.modules import research
from factory.modules.production import advance, back, create_project, gate_problems
from tests.helpers import add_source, make_sandbox, remove_sandbox, run_cli, tick_all

GOOD_SCRIPT = """# Script
## [SCENE 1] Hook
One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen [F1].
## [SCENE 2] Body
Sixteen seventeen eighteen nineteen twenty more words here to reach a sensible length for a short video.
Another sentence with several additional words so the estimate lands near the target length okay.
## Stage checklist
- [x] ok
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = create_project(self.ctx, "Gate project", "en", "psychology", seconds=30, created="2026-01-01")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        return run_cli(list(argv), self.ctx)

    def to_stage(self, stage):
        while self.p.stage != stage:
            advance(self.ctx, self.p, force=True)

    def script(self, text):
        (self.p.folder / "03_script/script.md").write_text(text, encoding="utf-8")

    def reload(self):
        return find_project(self.ctx, self.p.id)


# ----------------------------------------------------------- checks framework
class TestChecksFramework(unittest.TestCase):
    def setUp(self):
        self.saved = checks.registered()
        self.tmp, self.ctx = make_sandbox()
        self.p = create_project(self.ctx, "Framework", "en", "gaming", created="2026-01-01")

    def tearDown(self):
        checks._REGISTRY.clear()
        checks._REGISTRY.update(self.saved)
        remove_sandbox(self.tmp)

    def test_register_run_and_sort(self):
        @checks.register("research")
        def sample(ctx, project):
            return [Finding(INFO, "I1", "info"), Finding(WARN, "W1", "warn"), Finding(FAIL, "F1", "fail", "a.md")]
        checks.register("research")(sample)  # registering twice has no effect
        found = [f for f in run_checks(self.ctx, self.p) if f.code in ("I1", "W1", "F1")]  # ignore M2 source checks
        self.assertEqual([f.level for f in found], [FAIL, WARN, INFO])
        self.assertEqual([f.code for f in failures(found)], ["F1"])
        self.assertEqual(format_finding(found[0]), "FAIL F1 [a.md]: fail")
        self.assertEqual(format_finding(found[1]), "WARN W1: warn")
        already = len(self.saved.get("research", []))  # e.g. the M1 idea-link check
        self.assertEqual(len(checks.registered("research")), already + 1)

    def test_unknown_level_and_stage_rejected(self):
        @checks.register("research")
        def bad(ctx, project):
            return [Finding("OOPS", "X", "bad")]
        with self.assertRaises(ValueError):
            run_checks(self.ctx, self.p)
        with self.assertRaises(FactoryError):
            run_checks(self.ctx, self.p, "not-a-stage")

    def test_phase1_checks_are_registered(self):
        names = {s: [f.__name__ for f in fs] for s, fs in checks.registered().items()}
        self.assertIn("check_script", names["script"])
        self.assertIn("check_claims_covered", names["factcheck"])


# ------------------------------------------------------------------ gates
class TestGatesUseChecks(Base):
    def test_empty_script_blocks_even_when_ticked(self):
        self.to_stage("script")
        tick_all(self.p.folder / "03_script/script.md")
        blockers, fails = gate_problems(self.ctx, self.p)
        self.assertEqual(blockers, [])
        self.assertIn("SCRIPT_EMPTY_SCENE", {f.code for f in fails})
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        msg = str(e.exception)
        self.assertIn("Automated checks failed", msg)
        self.assertIn("FAIL SCRIPT_EMPTY_SCENE [03_script/script.md]", msg)
        self.assertIn(f"python -m factory check {self.p.id}", msg)
        self.assertNotIn("Stage checklist not complete", msg)

    def test_good_script_advances_and_warn_does_not_block(self):
        self.to_stage("script")
        self.script(GOOD_SCRIPT)
        self.assertEqual(gate_problems(self.ctx, self.p), ([], []))
        self.assertEqual(advance(self.ctx, self.p), "factcheck")
        self.assertNotIn("forced", self.p.meta["history"][-1])

    def test_missing_claim_blocks_factcheck(self):
        self.to_stage("script")
        self.script(GOOD_SCRIPT)
        advance(self.ctx, self.p)
        tick_all(self.p.folder / "04_factcheck/factcheck.md")
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        self.assertIn("FACTCHECK_MISSING_CLAIM", str(e.exception))
        fc = self.p.folder / "04_factcheck/factcheck.md"
        text = fc.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| F1 "))
        fc.write_text(text.replace(row, "| F1  | counting | S1 | ✅ | |"), encoding="utf-8")
        add_source(self.ctx, self.p)  # M5: a claim needs a verified source and a verdict
        research.set_verification(self.ctx, self.p, "S1", "verified")
        self.assertEqual(advance(self.ctx, self.p), "voice")

    def test_checklist_and_findings_reported_together(self):
        self.to_stage("script")
        code, out = self.cli("advance", "gate-project")
        self.assertEqual(code, 1)
        self.assertIn("Stage checklist not complete", out)   # Phase 1 wording kept
        self.assertIn("Automated checks failed", out)
        self.assertIn("Tick the boxes and fix the FAIL findings", out)

    def test_force_records_findings(self):
        self.to_stage("script")
        advance(self.ctx, self.p, force=True)
        entry = self.p.meta["history"][-1]
        self.assertTrue(entry["forced"])
        self.assertIn("SCRIPT_EMPTY_SCENE", entry["forced_findings"])
        self.assertIn("SCRIPT_LENGTH", entry["forced_findings"])

    def test_show_mentions_findings(self):
        self.to_stage("script")
        code, out = self.cli("show", "gate-project")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"Automated checks: \d+ FAIL, \d+ WARN")


# --------------------------------------------------------- check and back
class TestCheckCommand(Base):
    def test_current_stage(self):
        code, out = self.cli("check", "gate-project")
        self.assertEqual(code, 1)  # research checklist unticked
        self.assertIn("Research (current stage):", out)
        self.assertIn("CHECKLIST research.md:", out)
        tick_all(self.p.folder / "01_research/research.md")
        add_source(self.ctx, self.p)  # M2: a project needs a source to leave Research
        code, out = self.cli("check", "gate-project")
        self.assertEqual(code, 0, out)
        self.assertIn("no problems found", out)

    def test_other_stage_and_all(self):
        code, out = self.cli("check", "gate-project", "--stage", "script")
        self.assertEqual(code, 1)
        self.assertIn("SCRIPT_EMPTY_SCENE", out)
        code, out = self.cli("check", "gate-project", "--all")
        self.assertEqual(code, 1)
        self.assertIn("Script Writing:", out)
        code, out = self.cli("check", "gate-project", "--stage", "nope")
        self.assertEqual(code, 1)
        self.assertIn("Unknown stage 'nope'", out)

    def test_sample_project_has_no_fail(self):
        from factory.core.config import Context
        ctx = Context()
        p = find_project(ctx, "octopus")
        for stage in (s["id"] for s in ctx.config.stages):
            self.assertEqual(failures(run_checks(ctx, p, stage)), [], stage)


class TestBack(Base):
    def test_back_records_and_keeps_files(self):
        self.to_stage("script")
        before = {f: f.read_bytes() for f in self.p.folder.rglob("*") if f.is_file() and f.name != "project.json"}
        code, out = self.cli("back", "gate-project")
        self.assertEqual(code, 0, out)
        self.assertIn("Script Writing → back to Content Planning", out)
        p = self.reload()
        self.assertEqual(p.stage, "planning")
        self.assertEqual(p.meta["history"][-1]["back_from"], "script")
        self.assertEqual({f: f.read_bytes() for f in before}, before)

    def test_back_at_first_stage(self):
        with self.assertRaises(FactoryError) as e:
            back(self.ctx, self.p)
        self.assertIn("first stage", str(e.exception))

    def test_back_then_forward_again(self):
        self.to_stage("planning")
        back(self.ctx, self.p)
        tick_all(self.p.folder / "01_research/research.md")
        add_source(self.ctx, self.p)
        self.assertEqual(advance(self.ctx, self.p), "planning")


# ------------------------------------------------------------- rules.json
class TestRules(Base):
    def test_threshold_from_rules_json(self):
        self.to_stage("script")
        self.script(GOOD_SCRIPT)
        rules = self.tmp / "config/rules.json"

        def codes_with_tolerance(percent):
            data = json.loads(rules.read_text(encoding="utf-8"))
            data["script"]["target_tolerance_percent"] = percent
            rules.write_text(json.dumps(data), encoding="utf-8")
            self.ctx.config._cache.clear()
            return {f.code for f in run_checks(self.ctx, self.p)}
        self.assertNotIn("SCRIPT_TARGET", codes_with_tolerance(1000))
        self.assertIn("SCRIPT_TARGET", codes_with_tolerance(1))

    def test_broken_rules_json(self):
        self.to_stage("script")  # reach the stage first: Planning checks also read rules.json (M3)
        (self.tmp / "config/rules.json").write_text("{}", encoding="utf-8")
        self.ctx.config._cache.clear()
        code, out = self.cli("check", "gate-project")
        self.assertEqual(code, 1)
        self.assertIn("config/rules.json has a problem: missing 'script'", out)


# --------------------------------------------------- format versions, migrate
def checksums(folder):
    return {f.relative_to(folder).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(folder.rglob("*")) if f.is_file()}


class TestSchemaAndMigrate(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        # Real Phase 1 sample projects (format 1) copied into the sandbox
        import shutil
        for p in iter_projects(__import__("factory.core.config", fromlist=["Context"]).Context()):
            dest = self.tmp / p.folder.relative_to(ROOT)
            shutil.copytree(p.folder, dest)

    def tearDown(self):
        remove_sandbox(self.tmp)

    def test_new_projects_use_current_format(self):
        p = create_project(self.ctx, "Fresh", "ms", "gaming", created="2026-01-01")
        self.assertEqual(json.loads((p.folder / "project.json").read_text(encoding="utf-8"))["schema_version"],
                         CURRENT_SCHEMA)
        planned = sorted(project.id for project, _, _ in migrate.plan(self.ctx))
        self.assertNotIn(p.id, planned)  # new projects need no upgrade
        self.assertEqual(planned, ["2026-11-17_kenapa-sotong-kurita-ada-tiga-jantung",
                                   "2026-11-17_why-octopuses-have-three-hearts"])

    def test_phase1_projects_read_as_format_1(self):
        self.assertEqual(sorted(p.meta["schema_version"] for p in iter_projects(self.ctx)), [1, 1])
        self.assertEqual(self.ctx.warnings, {})

    def test_preview_changes_nothing(self):
        before = checksums(self.tmp)
        code, out = run_cli(["migrate"], self.ctx)
        self.assertEqual(code, 0, out)
        self.assertIn("Would upgrade", out)
        self.assertIn("Preview only: nothing was changed", out)
        self.assertEqual(checksums(self.tmp), before)

    def test_apply_only_sets_version_and_is_repeatable(self):
        before = checksums(self.tmp)
        metas = {p.id: json.loads((p.folder / "project.json").read_text(encoding="utf-8"))
                 for p in iter_projects(self.ctx)}
        code, out = run_cli(["migrate", "--apply"], self.ctx)
        self.assertEqual(code, 0, out)
        self.assertIn("Upgraded", out)
        after = checksums(self.tmp)
        changed = sorted(k for k in before if before[k] != after.get(k))
        self.assertTrue(all(k.endswith("/project.json") for k in changed), changed)
        added = sorted(k for k in after if k not in before)  # v3 (M2) adds only sources.csv
        self.assertEqual(added, sorted(f"{p.folder.relative_to(self.tmp).as_posix()}/01_research/sources.csv"
                                       for p in iter_projects(self.ctx)))
        for p in iter_projects(self.ctx):
            new = json.loads((p.folder / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(new.pop("schema_version"), CURRENT_SCHEMA)
            self.assertEqual(new, metas[p.id])  # nothing else changed
        snapshot = checksums(self.tmp)
        code, out = run_cli(["migrate", "--apply"], self.ctx)
        self.assertIn("All projects are up to date", out)
        self.assertEqual(checksums(self.tmp), snapshot)

    def test_add_missing_file_never_overwrites(self):
        p = find_project(self.ctx, "octopus")
        existing = p.folder / "01_research/research.md"
        original = existing.read_bytes()
        self.assertEqual(migrate.add_missing_file(self.ctx, p, "01_research/research.md", "research.md", {}, True), [])
        self.assertEqual(existing.read_bytes(), original)
        actions = migrate.add_missing_file(self.ctx, p, "01_research/extra.md", "research.md", {}, apply=False)
        self.assertEqual(actions, ["add 01_research/extra.md"])
        self.assertFalse((p.folder / "01_research/extra.md").exists())  # preview writes nothing
        migrate.add_missing_file(self.ctx, p, "01_research/extra.md", "research.md", {}, apply=True)
        self.assertTrue((p.folder / "01_research/extra.md").exists())

    def test_newer_or_invalid_format_is_reported(self):
        p = find_project(self.ctx, "kenapa")
        meta_path = p.folder / "project.json"
        for value, expected in ((CURRENT_SCHEMA + 1, "saved by a newer version of the factory"),
                                ("2", "'schema_version' must be a whole number"),
                                (0, "'schema_version' must be a whole number")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["schema_version"] = value
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            self.ctx.warnings.clear()
            code, out = run_cli(["status"], self.ctx)
            self.assertEqual(code, 0, out)
            self.assertIn(expected, out)
            self.assertNotIn("kenapa-sotong", out.split("Warning")[0])

    def test_damaged_projects_are_skipped_by_migrate(self):
        (find_project(self.ctx, "kenapa").folder / "project.json").write_text("{", encoding="utf-8")
        code, out = run_cli(["migrate", "--apply"], self.ctx)
        self.assertEqual(code, 0, out)
        self.assertIn("Skipped damaged project", out)
        self.assertEqual((find_project(self.ctx, "octopus").meta["schema_version"]), CURRENT_SCHEMA)

    def test_every_version_has_a_step(self):
        self.assertEqual(sorted(migrate.STEPS), list(range(2, CURRENT_SCHEMA + 1)))


# ----------------------------------------------------- cross-platform behaviour
class TestCrossPlatform(Base):
    def test_display_path_uses_forward_slashes(self):
        nested = self.tmp / "brands" / "qhaze" / "en" / "ideas.csv"
        self.assertEqual(display_path(nested, self.tmp), "brands/qhaze/en/ideas.csv")
        self.assertEqual(display_path(str(nested), str(self.tmp)), "brands/qhaze/en/ideas.csv")
        self.assertNotIn("\\", display_path(nested))
        self.assertEqual(display_path(None), "a file")

    def test_messages_use_forward_slashes(self):
        code, out = self.cli("new", "Slashes", "--lang", "ms", "--division", "gaming")
        self.assertIn("Created: brands/qhaze/ms/gaming/", out)
        code, out = self.cli("show", "slashes")
        self.assertIn("Folder   : brands/qhaze/ms/gaming/", out)
        self.assertNotIn("\\", out)

    def test_output_that_cannot_be_encoded_does_not_crash(self):
        """Windows redirects output in a code page without ✔ or Jawi letters."""
        create_project(self.ctx, "سوتوڠ کوريتا", "ms", "gaming", created="2026-01-01")
        raw = io.BytesIO()
        narrow = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        with mock.patch.object(sys, "stdout", narrow), mock.patch.object(sys, "stderr", narrow):
            self.to_stage("script")
            code = main(["show", "gate-project"], ctx=self.ctx)
            code2 = main(["status"], ctx=self.ctx)
            narrow.flush()
        self.assertEqual((code, code2), (0, 0))
        text = raw.getvalue().decode("cp1252")
        self.assertIn("? ", text)          # ✔ replaced
        self.assertIn("Gate project", text)

    def test_utf8_output_unchanged(self):
        raw = io.BytesIO()
        wide = io.TextIOWrapper(raw, encoding="utf-8")
        with mock.patch.object(sys, "stdout", wide):
            self.to_stage("planning")
            main(["show", "gate-project"], ctx=self.ctx)
            wide.flush()
        self.assertIn("✔", raw.getvalue().decode("utf-8"))

    def test_crlf_files_are_read_correctly(self):
        """Windows checkouts and editors use CRLF line endings."""
        research = self.p.folder / "01_research/research.md"
        research.write_bytes(research.read_bytes().replace(b"\n", b"\r\n"))
        code, out = self.cli("advance", "gate-project")
        self.assertIn("research.md: At least 2 credible sources recorded", out)
        self.assertNotIn("\r", out)
        tick_all(research)
        add_source(self.ctx, self.p)
        self.assertEqual(advance(self.ctx, self.p), "planning")
        self.to_stage("script")
        (self.p.folder / "03_script/script.md").write_bytes(GOOD_SCRIPT.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(failures(run_checks(self.ctx, self.p)), [])


# -------------------------------------------------------- regression guards
class TestRegressionGuards(unittest.TestCase):
    FILES = sorted(ROOT.glob("factory/**/*.py")) + sorted(ROOT.glob("tests/*.py"))

    def test_every_text_file_access_names_an_encoding(self):
        """Windows defaults to cp1252: every text read/write must say encoding=."""
        problems = []
        for path in self.FILES:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or any(k.arg == "encoding" for k in node.keywords):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
                    problems.append(f"{path.name}:{node.lineno}")
                elif isinstance(func, ast.Name) and func.id == "open":
                    mode = node.args[1] if len(node.args) > 1 else next(
                        (k.value for k in node.keywords if k.arg == "mode"), None)
                    if isinstance(mode, ast.Constant) and "b" in str(mode.value):
                        continue
                    if mode is not None and not isinstance(mode, ast.Constant):
                        continue
                    problems.append(f"{path.name}:{node.lineno}")
        self.assertEqual(problems, [], "text file access without encoding=")

    def test_paths_shown_to_users_go_through_display_path(self):
        offenders = []
        for path in sorted(ROOT.glob("factory/**/*.py")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"relative_to\(ctx\.paths\.root\)", line):
                    offenders.append(f"{path.name}:{n}")
        self.assertEqual(offenders, [])

    def test_ci_workflow(self):
        wf = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        self.assertIn('os: ubuntu-24.04,   python: "3.9",  experimental: false', wf)  # no 3.9 on 26.04
        for version in ("3.10", "3.11", "3.12", "3.13"):
            self.assertIn(f'os: ubuntu-latest,  python: "{version}", experimental: false', wf)
        self.assertIn('os: windows-latest, python: "3.13", experimental: false', wf)
        self.assertIn('os: macos-latest,   python: "3.13", experimental: false', wf)
        self.assertIn('python: "3.14", experimental: true', wf)
        self.assertIn("continue-on-error: ${{ matrix.experimental }}", wf)
        self.assertIn("permissions:\n  contents: read", wf)
        self.assertIn("pull_request:", wf)
        self.assertIn("python -m unittest discover -s tests", wf)
        self.assertIn('PYTHONUTF8: "0"', wf)
        self.assertNotIn("secrets.", wf)
        self.assertNotRegex(wf, r"pip install|requirements")  # no dependencies installed
        uses = re.findall(r"uses: ([\w./-]+)@", wf)
        self.assertEqual(sorted(set(uses)), ["actions/checkout", "actions/setup-python"])

    def test_gitattributes_normalises_line_endings(self):
        self.assertIn("* text=auto", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_no_voice_or_paid_api_code(self):
        pattern = re.compile(r"voice.?studio|elevenlabs|text.to.speech|\btts\b|urlopen|requests\b|api[_-]?key", re.I)
        for path in sorted(ROOT.glob("factory/**/*.py")) + sorted((ROOT / "config").glob("*.json")) + \
                [ROOT / ".github/workflows/tests.yml"]:
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path)


if __name__ == "__main__":
    unittest.main()
