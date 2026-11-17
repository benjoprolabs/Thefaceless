"""Tests for the v0.3.2 round:
1. --idea / --lang conflicts
2. Friendly file permission (and other file-system) errors
3. Python 3.9 / 3.10 compatibility guards
"""

import ast
import builtins
import errno
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from factory.core.config import ROOT, FactoryError
from factory.core.errors import describe_os_error
from factory.core.files import read_csv
from factory.core.projects import iter_projects
from factory.core.validation import check_date
from factory.modules.production import create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()

    def tearDown(self):
        remove_sandbox(self.tmp)

    def cli(self, *argv):
        return run_cli(list(argv), self.ctx)

    def idea(self, lang, idea_id):
        return next(i for i in read_csv(self.ctx.paths.ideas_csv("qhaze", lang)) if i["id"] == idea_id)


# --------------------------------------------------------------------- 1
class TestIdeaLangConflict(Base):
    def test_conflicting_lang_is_a_clear_error(self):
        code, out = self.cli("new", "--idea", "EN-002", "--lang", "ms")
        self.assertEqual(code, 1)
        self.assertIn("Conflicting options: idea EN-002 is in the English backlog (en), "
                      "but --lang ms (Bahasa Melayu) was given.", out)
        self.assertIn("python -m factory new --idea EN-002", out)
        self.assertIn("python -m factory ideas add \"<Bahasa Melayu title>\" --lang ms "
                      "--division what-if-science --format long", out)
        self.assertEqual(list(iter_projects(self.ctx)), [])          # nothing created
        self.assertEqual(self.idea("en", "EN-002")["status"], "backlog")  # idea untouched

    def test_conflict_other_direction(self):
        code, out = self.cli("new", "--idea", "MS-002", "--lang", "en")
        self.assertEqual(code, 1)
        self.assertIn("idea MS-002 is in the Bahasa Melayu backlog (ms), but --lang en (English)", out)

    def test_matching_lang_is_allowed_any_case(self):
        for argv in (["new", "--idea", "EN-002", "--lang", "en"], ["new", "--idea", "MS-002", "--lang", "MS"]):
            code, out = self.cli(*argv)
            self.assertEqual(code, 0, out)
        self.assertEqual(sorted(p.language for p in iter_projects(self.ctx)), ["en", "ms"])

    def test_without_lang_and_overrides_still_work(self):
        code, out = self.cli("new", "Custom title", "--idea", "EN-002", "--division", "gaming", "--format", "short")
        self.assertEqual(code, 0, out)
        p = next(iter_projects(self.ctx))
        self.assertEqual((p.meta["title"], p.meta["division"], p.meta["format"], p.language),
                         ("Custom title", "gaming", "short", "en"))

    def test_invalid_lang_still_reported_first(self):
        code, out = self.cli("new", "--idea", "EN-002", "--lang", "fr")
        self.assertEqual(code, 1)
        self.assertIn("Unknown language 'fr'", out)


# --------------------------------------------------------------------- 2
def deny(match, modes="w"):
    """Patch builtins.open so opening a path containing `match` in one of `modes` fails."""
    real_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if match in str(file) and any(m in mode for m in modes):
            raise PermissionError(errno.EACCES, "Permission denied", str(file))
        return real_open(file, mode, *args, **kwargs)
    return mock.patch("builtins.open", fake_open)


class TestFriendlyFileErrors(Base):
    def assert_friendly(self, code, out, *expected):
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("PermissionError", out)
        for text in expected:
            self.assertIn(text, out)

    def test_locked_ideas_csv_on_add(self):
        before = self.ctx.paths.ideas_csv("qhaze", "en").read_bytes()
        with deny("ideas.csv"):
            code, out = self.cli("ideas", "add", "T", "--lang", "en", "--division", "gaming")
        self.assert_friendly(code, out, "Permission denied: cannot access 'brands/qhaze/en/ideas.csv'",
                             "open in another program (for example Excel)")
        self.assertEqual(self.ctx.paths.ideas_csv("qhaze", "en").read_bytes(), before)

    def test_unreadable_ideas_csv_on_list(self):
        real_read = Path.read_bytes

        def fail_on_ideas(self_path):
            if self_path.name == "ideas.csv":
                raise PermissionError(errno.EACCES, "Permission denied", str(self_path))
            return real_read(self_path)
        with mock.patch.object(Path, "read_bytes", fail_on_ideas):
            code, out = self.cli("ideas", "--lang", "ms")
        self.assert_friendly(code, out, "Permission denied", "brands/qhaze/ms/ideas.csv")

    def test_new_project_write_failure_leaves_nothing_behind(self):
        real_write = Path.write_text

        def fail_on_qc(self_path, *args, **kwargs):
            if self_path.name == "qc.md":
                raise PermissionError(errno.EACCES, "Permission denied", str(self_path))
            return real_write(self_path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", fail_on_qc):
            code, out = self.cli("new", "Half made", "--lang", "en", "--division", "gaming")
        self.assert_friendly(code, out, "Permission denied", "qc.md")
        self.assertFalse(any(self.tmp.glob("brands/qhaze/en/gaming/*half-made*")))
        code, out = self.cli("new", "Half made", "--lang", "en", "--division", "gaming")  # retry works
        self.assertEqual(code, 0, out)

    def test_project_created_but_idea_list_locked(self):
        with deny("ideas.csv"):
            code, out = self.cli("new", "--idea", "EN-002")
        self.assert_friendly(code, out, "was created, but the idea list could not be updated",
                             "Permission denied", "set EN-002 to status 'in_production'")
        self.assertEqual(len(list(iter_projects(self.ctx))), 1)

    def test_unreadable_project_json_is_skipped_with_reason(self):
        create_project(self.ctx, "Locked", "en", "gaming", created="2026-01-01")
        create_project(self.ctx, "Fine", "en", "gaming", created="2026-01-01")
        real_read = Path.read_bytes

        def fail_on_locked(self_path):
            if self_path.as_posix().endswith("locked/project.json"):
                raise PermissionError(errno.EACCES, "Permission denied", str(self_path))
            return real_read(self_path)
        with mock.patch.object(Path, "read_bytes", fail_on_locked):
            code, out = self.cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn("2026-01-01_fine", out)
        self.assertIn("Skipped damaged project", out)
        self.assertIn("permission denied (your account can't read this file)", out)

    def test_saving_project_json_denied(self):
        create_project(self.ctx, "Adv", "en", "gaming", created="2026-01-01")
        with mock.patch("factory.core.projects.write_json",
                        side_effect=PermissionError(errno.EACCES, "Permission denied", "x/project.json")):
            code, out = self.cli("advance", "adv", "--force")
        self.assert_friendly(code, out, "Permission denied: cannot access 'x/project.json'")

    def test_missing_config_folder(self):
        import shutil
        shutil.rmtree(self.tmp / "config")
        code, out = self.cli("status")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertIn("File or folder not found", out)
        self.assertIn("config/settings.json", out)

    def test_describe_os_error_variants(self):
        cases = [
            (FileNotFoundError(errno.ENOENT, "No such file", "/x/a.csv"), "File or folder not found: '/x/a.csv'"),
            (IsADirectoryError(errno.EISDIR, "Is a directory", "/x/dir"), "Expected a file but found a folder"),
            (NotADirectoryError(errno.ENOTDIR, "Not a directory", "/x/f"), "Expected a folder but found a file"),
            (OSError(errno.ENOSPC, "No space left", "/x/b.csv"), "Not enough disk space to save '/x/b.csv'"),
            (OSError(errno.EROFS, "Read-only file system", "/x/c.csv"), "the disk or folder is read-only"),
            (OSError(errno.EIO, "Input/output error", "/x/d.csv"), "Could not access '/x/d.csv': Input/output error."),
            (PermissionError(errno.EACCES, "Permission denied"), "Permission denied: cannot access 'a file'"),
        ]
        for error, expected in cases:
            self.assertIn(expected, describe_os_error(error))
        self.assertIn("'brands/a.csv'", describe_os_error(
            PermissionError(errno.EACCES, "x", str(self.tmp / "brands/a.csv")), self.tmp))

    @unittest.skipIf(IS_ROOT or os.name != "posix", "needs a non-root POSIX user (root ignores permissions)")
    def test_real_read_only_files(self):
        csv_path = self.ctx.paths.ideas_csv("qhaze", "en")
        os.chmod(csv_path, 0o444)
        try:
            code, out = self.cli("ideas", "add", "T", "--lang", "en", "--division", "gaming")
            self.assert_friendly(code, out, "Permission denied", "brands/qhaze/en/ideas.csv")
        finally:
            os.chmod(csv_path, 0o644)
        division_dir = self.tmp / "brands/qhaze/en/gaming"
        division_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(division_dir, 0o555)
        try:
            code, out = self.cli("new", "Blocked", "--lang", "en", "--division", "gaming")
            self.assert_friendly(code, out, "Permission denied")
        finally:
            os.chmod(division_dir, 0o755)


# --------------------------------------------------------------------- 3
class TestPythonCompatibility(unittest.TestCase):
    FILES = sorted(ROOT.glob("factory/**/*.py")) + sorted(ROOT.glob("tests/*.py"))

    def test_all_code_parses_with_python_39_and_310_grammar(self):
        self.assertGreater(len(self.FILES), 20)
        for path in self.FILES:
            for version in ((3, 9), (3, 10)):
                with self.subTest(file=path.name, version=version):
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=version)

    def test_no_newer_standard_library_features(self):
        newer = {
            r"^\s*match\s+[^=]+:\s*$": "match statement (3.10)",
            r"zip\([^)]*strict\s*=": "zip(strict=) (3.10)",
            r"\bpairwise\(|\bbatched\(": "itertools (3.10/3.12)",
            r"\btomllib\b|\bStrEnum\b|contextlib\.chdir|datetime\.UTC|hashlib\.file_digest": "3.11",
            r"except\s*\*|ExceptionGroup": "exception groups (3.11)",
            r"isinstance\([^)]*\w\s*\|\s*\w": "X | Y in isinstance (3.10)",
            r"\)\s*->\s*[\w\[\]]+\s*\|": "X | Y return annotation (3.10)",
            r"onexc\s*=|\.walk\(\)": "3.12",
        }
        for path in self.FILES:
            if path.name == "test_compat_errors.py":
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for pattern, why in newer.items():
                    self.assertIsNone(re.search(pattern, line), f"{path.name}:{n} uses {why}: {line.strip()}")

    def test_only_standard_library_imports(self):
        stdlib = {"argparse", "ast", "builtins", "collections", "contextlib", "csv", "datetime", "errno",
                  "fnmatch", "hashlib", "io", "json", "os", "pathlib", "re", "shutil", "stat", "subprocess",
                  "sys", "tempfile", "unittest", "urllib"}
        for path in self.FILES:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    self.assertIn(top, stdlib | {"factory", "tests"}, f"{path.name} imports {name}")

    def test_date_rule_identical_on_all_versions(self):
        self.assertEqual(check_date("2026-01-05"), "2026-01-05")
        for value in ("20260105", "2026-W02-1", "2026-01-05T10:00", "2026-1-5", " 2026-01-05", "2026-02-30"):
            with self.assertRaises(FactoryError, msg=value):
                check_date(value)

    def test_old_python_gets_a_clear_message(self):
        code = ("import sys; sys.version_info = (3, 8, 10, 'final', 0); import runpy; "
                "runpy.run_module('factory', run_name='__main__')")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("needs Python 3.9 or newer; this is Python 3.8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_minimum_version_documented(self):
        self.assertIn("Python 3.9+", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
