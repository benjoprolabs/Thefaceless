"""Tests for M5 Fact-Checking System (v0.4.5): factcheck.md reading, sync
(adds rows only, never changes edited rows), every Fact check rule in
PHASE2_PLAN.md §7, report, and the Fact Check gate."""

import hashlib
import unittest

from factory.core.checks import FAIL, WARN, failures, run_checks
from factory.core.config import Context, FactoryError
from factory.core.projects import find_project
from factory.modules import factcheck, research
from factory.modules.production import advance, create_project
from tests.helpers import make_sandbox, remove_sandbox, run_cli, tick_all

SCRIPT = """# Script

## [SCENE 1] Hook
<!-- Visual: x -->
Octopuses have three hearts [F1]. Their blood is blue [F2].

## [SCENE 2] End
One heart stops when they swim [F3]. Follow for more.

## Stage checklist
- [x] done
"""


def table(*rows):
    """factcheck.md with a claims table made of the given row lines."""
    return ("# Fact Check\n\n| Ref | Claim | Source(s) | Verdict | Fix applied |\n"
            "|-----|-------|-----------|---------|-------------|\n" + "".join(r + "\n" for r in rows)
            + "\nVerdicts: ✅ · ⚠️ · ❌\n\n## Stage checklist\n- [x] done\n")


GOOD_ROWS = ("| F1 | Octopuses have three hearts | S1 | ✅ | |",
             "| F2 | Their blood is blue | S1, S2 | ok | |",
             "| F3 | One heart stops | S2 | ⚠️ | said 'pauses' |")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = self.new("Fact test")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def new(self, title, lang="en"):
        p = create_project(self.ctx, title, lang, "what-if-science", "short", created="2026-01-01")
        (p.folder / "03_script/script.md").write_text(SCRIPT, encoding="utf-8")
        return p

    def sources(self, *statuses, p=None, reliability=None):
        """Add one source per status (S1, S2, ...)."""
        p = p or self.p
        for i, status in enumerate(statuses, 1):
            research.add_source(self.ctx, p, f"Source {i}", f"https://www.example.org/s{i}", "study", "today",
                                reliability=reliability)
            if status != "unverified":
                research.set_verification(self.ctx, p, f"S{i}", status)

    def fc(self, p=None):
        return factcheck.factcheck_path(self.ctx, p or self.p)

    def write(self, *rows, p=None):
        self.fc(p).write_text(table(*rows), encoding="utf-8")

    def findings(self, p=None):
        return [(f.level, f.code) for f in factcheck.check_factcheck(self.ctx, p or self.p)]

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


# ------------------------------------------------------------ reading
class TestReading(unittest.TestCase):
    def test_verdicts(self):
        for text, verdict in (("✅", "ok"), ("OK", "ok"), ("⚠️", "soft"), ("⚠", "soft"), ("Soft", "soft"),
                              ("❌", "remove"), ("remove", "remove"), ("", None), ("✅ / ⚠️ / ❌", None),
                              ("maybe", "invalid"), ("✅ ❌", "invalid")):
            self.assertEqual(factcheck.parse_verdict(text), verdict, text)

    def test_rows_sources_and_escaped_pipes(self):
        rows = factcheck.parse_rows(table("| F1 | a \\| b | S1, s3 | ✅ | |", "| F12 | x | S2;S4 S5 | ❌ | gone |",
                                          "| not a claim | | | | |", "| F3 |"))
        self.assertEqual([r["ref"] for r in rows], [1, 12, 3])
        self.assertEqual(rows[0]["claim"], "a | b")
        self.assertEqual(rows[0]["sources"], ["S1", "S3"])
        self.assertEqual(rows[1]["sources"], ["S2", "S4", "S5"])
        self.assertEqual((rows[1]["verdict"], rows[1]["fix"]), ("remove", "gone"))
        self.assertEqual((rows[2]["claim"], rows[2]["verdict"]), ("", None))  # short row padded

    def test_template_row_is_blank(self):
        tmp, ctx = make_sandbox()
        try:
            p = create_project(ctx, "Template", "en", "psychology", "short", created="2026-01-01")
            rows = factcheck.parse_rows(factcheck.factcheck_path(ctx, p).read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertTrue(factcheck.row_is_blank(rows[0]))
        finally:
            remove_sandbox(tmp)


# ------------------------------------------------------------ sync
class TestSync(Base):
    def test_fills_template_row_and_adds_missing_rows(self):
        before = self.fc().read_text(encoding="utf-8")
        out = self.ok("factcheck", "sync", "fact-test")
        self.assertIn("Filled blank row(s): F1", out)
        self.assertIn("Added row(s): F2, F3", out)
        rows = factcheck.parse_rows(self.fc().read_text(encoding="utf-8"))
        self.assertEqual([(r["ref"], r["claim"]) for r in rows],
                         [(1, "Octopuses have three hearts."), (2, "Their blood is blue."),
                          (3, "One heart stops when they swim.")])
        self.assertTrue(all(r["verdict"] is None and not r["sources"] for r in rows))
        # every other line is unchanged
        after = self.fc().read_text(encoding="utf-8")
        kept = [l for l in before.splitlines() if not l.startswith("| F1 ")]
        self.assertEqual([l for l in after.splitlines() if not l.startswith(("| F1 ", "| F2 ", "| F3 "))], kept)
        self.assertIn("Nothing changed", self.ok("factcheck", "sync", "fact-test"))
        self.assertEqual(self.fc().read_text(encoding="utf-8"), after)

    def test_never_changes_edited_rows(self):
        edited = ("| F1 | my own wording | S9 | ❌ | removed |", "| F3 |  | S1 |  | |")
        self.write(*edited)
        before = self.fc().read_bytes()
        self.assertIn("Added row(s): F2", self.ok("factcheck", "sync", "fact-test"))
        after = self.fc().read_text(encoding="utf-8")
        for line in edited:
            self.assertIn(line, after)
        # Byte-for-byte: only the new row was added, with the file's own line ending
        # (the file has CRLF endings when written in text mode on Windows).
        newline = b"\r\n" if b"\r\n" in before else b"\n"
        added = "| F2  | Their blood is blue. | | | |".encode("utf-8") + newline
        self.assertEqual(self.fc().read_bytes().replace(added, b""), before)
        rows = factcheck.parse_rows(after)
        self.assertEqual([r["ref"] for r in rows], [1, 3, 2])  # added after the last claim row

    def test_new_claims_after_script_edit(self):
        self.write(*GOOD_ROWS)
        script = self.p.folder / "03_script/script.md"
        script.write_text(SCRIPT.replace("Follow for more.", "It has nine brains [F4]. Follow for more."),
                          encoding="utf-8")
        self.ok("factcheck", "sync", "fact-test")
        rows = factcheck.parse_rows(self.fc().read_text(encoding="utf-8"))
        self.assertEqual(rows[-1]["claim"], "It has nine brains.")
        self.assertEqual([r["claim"] for r in rows[:3]], [l.split("|")[2].strip() for l in GOOD_ROWS])

    def test_crlf_file_keeps_its_line_endings(self):
        crlf = table(GOOD_ROWS[0]).replace("\n", "\r\n").encode("utf-8")
        self.fc().write_bytes(crlf)
        self.ok("factcheck", "sync", "fact-test")
        data = self.fc().read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertTrue(data.startswith(crlf[:crlf.index(b"\r\n\r\nVerdicts")]))

    def test_no_table_and_missing_file(self):
        self.fc().write_text("# Fact Check\n\nNo table here.\n", encoding="utf-8")
        self.assertIn("no claims table", self.bad("factcheck", "sync", "fact-test"))
        self.fc().unlink()
        self.assertIn("factcheck.md is missing", self.bad("factcheck", "sync", "fact-test"))

    def test_malay_project(self):
        ms = self.new("Ujian fakta", lang="ms")
        (ms.folder / "03_script/script.md").write_text(
            "## [SCENE 1] Cangkuk\nSotong kurita ada tiga jantung [F1]. Langgan sekarang.\n", encoding="utf-8")
        self.ok("factcheck", "sync", ms.id)
        rows = factcheck.parse_rows(self.fc(ms).read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["claim"], "Sotong kurita ada tiga jantung.")


# ------------------------------------------------------------ rules (plan §7)
class TestRules(Base):
    def setUp(self):
        super().setUp()
        self.sources("verified", "verified")

    def test_good_table_passes(self):
        self.write(*GOOD_ROWS)
        self.assertEqual(self.findings(), [])
        self.assertIn("Fact check OK", self.ok("factcheck", "check", "fact-test"))

    def test_missing_row_uses_the_existing_rule(self):
        self.write(*GOOD_ROWS[:2])
        self.assertIn("FACTCHECK_MISSING_CLAIM", self.bad("factcheck", "check", "fact-test"))

    def test_no_verdict_and_invalid_verdict(self):
        self.write("| F1 | c | S1 |  | |", "| F2 | c | S1 | ✅ / ⚠️ / ❌ | |", "| F3 | c | S1 | maybe | |")
        self.assertEqual(self.findings(), [(FAIL, "FACTCHECK_NO_VERDICT"), (FAIL, "FACTCHECK_NO_VERDICT"),
                                           (FAIL, "FACTCHECK_VERDICT")])

    def test_no_source_and_unknown_source(self):
        self.write("| F1 | c |  | ✅ | |", "| F2 | c | S1, S7 | ✅ | |", "| F3 | c | 2 | ✅ | |")
        found = factcheck.check_factcheck(self.ctx, self.p)
        self.assertEqual([(f.level, f.code) for f in found],
                         [(FAIL, "FACTCHECK_NO_SOURCE"), (FAIL, "FACTCHECK_UNKNOWN_SOURCE"),
                          (FAIL, "FACTCHECK_UNKNOWN_SOURCE")])
        self.assertIn("F2 cites S7", found[1].message)
        self.assertIn("cite sources by ID", found[2].message)

    def test_removed_claim_still_in_script(self):
        self.write(GOOD_ROWS[0], GOOD_ROWS[1], "| F3 | One heart stops |  | ❌ | |")
        self.assertEqual(self.findings(), [(FAIL, "FACTCHECK_REMOVED_IN_SCRIPT")])
        script = self.p.folder / "03_script/script.md"
        script.write_text(SCRIPT.replace("One heart stops when they swim [F3]. ", ""), encoding="utf-8")
        self.assertEqual(self.findings(), [])  # removed from the script: ❌ needs nothing else

    def test_soft_claim_needs_a_fix(self):
        self.write(GOOD_ROWS[0], GOOD_ROWS[1], "| F3 | One heart stops | S2 | soft | |")
        self.assertEqual(self.findings(), [(FAIL, "FACTCHECK_NO_FIX")])

    def test_weak_sources(self):
        tmp, ctx = self.tmp, self.ctx
        p = self.new("Weak sources")
        self.sources("verified", "unverified", "disputed", "outdated", p=p)
        for cited, expected in (("S2", True), ("S3", True), ("S4", True), ("S2, S3, S4", True),
                                ("S2, S1", False), ("S1", False)):
            self.write(f"| F1 | c | {cited} | ✅ | |", GOOD_ROWS[1].replace("S1, S2", "S1"),
                       GOOD_ROWS[2].replace("S2", "S1"), p=p)
            codes = self.codes(p)
            self.assertEqual("FACTCHECK_WEAK_SOURCES" in codes, expected, cited)
        self.write("| F1 | c | S2 | ✅ | |", GOOD_ROWS[1].replace("S1, S2", "S1"), GOOD_ROWS[2].replace("S2", "S1"), p=p)
        message = [f.message for f in factcheck.check_factcheck(ctx, p)][0]
        self.assertIn("S2 unverified", message)
        self.assertIn("research verify", message)

    def test_low_reliability_warns(self):
        p = self.new("Low reliability")
        self.sources("verified", p=p, reliability=2)
        research.add_source(self.ctx, p, "Better", "https://www.example.org/b", "study", "today", reliability=4)
        research.set_verification(self.ctx, p, "S2", "verified")
        rows = ("| F1 | c | S1 | ✅ | |", "| F2 | c | S2 | ✅ | |", "| F3 | c | S1, S2 | ✅ | |")
        self.write(*rows, p=p)
        self.assertEqual(self.findings(p), [(WARN, "FACTCHECK_LOW_RELIABILITY")])

    def test_rows_for_claims_not_in_the_script_and_duplicates(self):
        self.write(*GOOD_ROWS, "| F9 | old claim |  |  | |", GOOD_ROWS[0].replace("S1", ""))
        self.assertEqual(self.findings(), [(WARN, "FACTCHECK_DUPLICATE_ROW")])  # F9 is no longer in the script

    def test_broken_sources_file(self):
        research.sources_path(self.ctx, self.p).write_text("title,notes\nx,y\n", encoding="utf-8")
        self.write(*GOOD_ROWS)
        self.assertEqual(self.findings(), [(FAIL, "FACTCHECK_SOURCES_FILE")])

    def test_project_past_fact_check_gets_warnings(self):
        self.write("| F1 | c | S7 | ✅ | |", *GOOD_ROWS[1:])
        self.p.meta["stage"] = "voice"
        self.p.save()
        found = factcheck.check_factcheck(self.ctx, self.p)
        self.assertEqual([(f.level, f.code) for f in found], [(WARN, "FACTCHECK_UNKNOWN_SOURCE")])
        self.assertIn("already past Fact Check", found[0].message)


# ------------------------------------------------------------ report
class TestReport(Base):
    def test_report(self):
        self.sources("verified", "disputed")
        self.write("| F1 | Octopuses have three hearts | S1 | ✅ | |", "| F2 | Blue blood | S2, S9 | ⚠️ | |",
                   "| F7 | Old claim | S1 | ❌ | removed |")
        out = self.ok("factcheck", "report", "fact-test")
        self.assertIn("Claims in the script: 3   Rows: 3", out)
        self.assertIn("✅ 1  ⚠️ 1  ❌ 1  no verdict 1", out)  # F3 has no row
        self.assertIn("S1 (verified)", out)
        self.assertIn("S2 (disputed), S9 (not found)", out)
        self.assertRegex(out, r"F3\s+no row\s+yes")
        self.assertRegex(out, r"F7\s+❌\s+no")
        self.assertIn("FAIL", out.splitlines()[-1])


# ------------------------------------------------------------ gate
class TestGate(Base):
    def setUp(self):
        super().setUp()
        self.p.meta["stage"] = "factcheck"
        self.p.save()
        self.sources("verified", "unverified")
        tick_all(self.fc())

    def blocked_by(self, code):
        tick_all(self.fc())
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        self.assertIn(code, str(e.exception))

    def test_each_rule_blocks_and_a_good_table_advances(self):
        self.write(GOOD_ROWS[0], GOOD_ROWS[1], "| F3 | One heart stops | S2 | ❌ | |")
        self.blocked_by("FACTCHECK_REMOVED_IN_SCRIPT")
        self.write(GOOD_ROWS[0], GOOD_ROWS[1], "| F3 | One heart stops | S1 | ⚠️ | |")
        self.blocked_by("FACTCHECK_NO_FIX")
        self.write(GOOD_ROWS[0], GOOD_ROWS[1], "| F3 | One heart stops | S2 | ✅ | |")
        self.blocked_by("FACTCHECK_WEAK_SOURCES")  # S2 is unverified
        self.ok("research", "verify", "fact-test", "S2", "verified")
        self.write(*GOOD_ROWS)
        tick_all(self.fc())
        self.assertEqual(failures(run_checks(self.ctx, self.p)), [])
        self.assertEqual(advance(self.ctx, self.p), "voice")

    def test_force_is_recorded(self):
        self.write(*GOOD_ROWS[:2])
        tick_all(self.fc())
        advance(self.ctx, self.p, force=True)
        self.assertIn("FACTCHECK_MISSING_CLAIM", self.p.meta["history"][-1]["forced_findings"])


class TestSamplesUnchanged(unittest.TestCase):
    def test_english_sample_has_no_fail_and_is_not_changed(self):
        ctx = Context()
        octopus = find_project(ctx, "octopus")
        path = factcheck.factcheck_path(ctx, octopus)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        # Phase 1 sample: rows cite research.md numbers and it has no sources.csv yet (migrated in M11).
        # It is past Fact Check, so these are warnings only.
        found = factcheck.check_factcheck(ctx, octopus)
        self.assertEqual({f.level for f in found}, {WARN})
        self.assertEqual({f.code for f in found}, {"FACTCHECK_UNKNOWN_SOURCE"})
        self.assertEqual(factcheck.report(ctx, octopus)["counts"]["ok"], 3)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
