"""Tests for M3 Content Planning (v0.4.3): plan.md reading, every Planning rule
(plan §7), plan set-date, plan calendar (filters, clashes) and the gate."""

import hashlib
import json
import unittest

from factory.core.checks import FAIL, WARN
from factory.core.config import Context, FactoryError
from factory.core.projects import find_project
from factory.modules import planning
from factory.modules.production import advance, create_project
from tests.helpers import add_source, make_sandbox, remove_sandbox, run_cli, tick_all


def fill(text, hook="A strong hook.", points=("Hook", "Point two", "Point three", "Payoff"),
         keyword="octopus hearts", when="2026-12-01"):
    """Fill a template plan.md."""
    outline = "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))
    start = text.index("## Outline")
    end = text.index("## SEO")
    text = text[:start] + f"## Outline\n{outline}\n\n" + text[end:]
    text = text.replace("## Angle / hook\n", f"## Angle / hook\n{hook}\n", 1)
    text = text.replace("- **Primary keyword:**", f"- **Primary keyword:** {keyword}", 1)
    return text.replace("## Target publish date\n", f"## Target publish date\n{when}\n", 1)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = self.new("Plan test")

    def tearDown(self):
        remove_sandbox(self.tmp)

    def new(self, title, lang="en", division="psychology", fmt="short", seconds=None):
        return create_project(self.ctx, title, lang, division, fmt, seconds=seconds, created="2026-01-01")

    def plan_file(self, p=None):
        return planning.plan_path(self.ctx, p or self.p)

    def write_plan(self, p=None, **kw):
        path = self.plan_file(p)
        path.write_text(fill(path.read_text(encoding="utf-8"), **kw), encoding="utf-8")

    def codes(self, p=None):
        return [(f.level, f.code) for f in planning.check_plan(self.ctx, p or self.p)]

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
        self.assertNotIn("Traceback", out)
        return out


class TestParsing(unittest.TestCase):
    def test_parse_filled_plan(self):
        text = ("## Angle / hook\n<!-- hint -->\nNobody watches.\n\n## Outline\n1. Hook\n2) Second\n3.\n4. Fourth\n\n"
                "## SEO\n- **Primary keyword:**\n- **Secondary keywords:** a, b\n\n## Target publish date\n2026-12-01\n")
        plan = planning.parse_plan(text)
        self.assertEqual(plan["hook"], "Nobody watches.")
        self.assertEqual(plan["outline"], ["Hook", "Second", "Fourth"])  # empty "3." not counted
        self.assertEqual(plan["primary_keyword"], "")  # empty value doesn't run into the next line
        self.assertEqual(plan["secondary_keywords"], "a, b")
        self.assertEqual((plan["date"], plan["missing_sections"]), ("2026-12-01", []))

    def test_missing_sections_and_crlf(self):
        plan = planning.parse_plan("## Outline\r\n1. a\r\n2. b\r\n3. c\r\n")
        self.assertEqual(plan["outline"], ["a", "b", "c"])
        self.assertEqual(plan["missing_sections"], ["Angle / hook", "SEO", "Target publish date"])


class TestRules(Base):
    def test_template_plan_fails_each_rule(self):
        self.assertEqual(self.codes(), [(FAIL, "PLAN_HOOK"), (FAIL, "PLAN_OUTLINE"), (FAIL, "PLAN_KEYWORD"),
                                        (FAIL, "PLAN_DATE")])

    def test_filled_plan_passes(self):
        self.write_plan()
        self.assertEqual(self.codes(), [])
        self.assertIn("Plan OK.", self.ok("plan", "check", "plan-test"))

    def test_each_rule_on_its_own(self):
        template = self.plan_file().read_text(encoding="utf-8")
        for kw, code in (({"hook": ""}, "PLAN_HOOK"), ({"points": ("a", "b")}, "PLAN_OUTLINE"),
                         ({"keyword": ""}, "PLAN_KEYWORD"), ({"when": ""}, "PLAN_DATE"),
                         ({"when": "01-12-2026"}, "PLAN_DATE"), ({"when": "2026-02-30"}, "PLAN_DATE")):
            self.plan_file().write_text(fill(template, **kw), encoding="utf-8")
            self.assertEqual(self.codes(), [(FAIL, code)], kw)
        self.assertIn("1 FAIL", self.bad("plan", "check", "plan-test"))

    def test_missing_section_and_missing_file(self):
        self.write_plan()
        path = self.plan_file()
        path.write_text(path.read_text(encoding="utf-8").replace("## SEO", "## Keywords"), encoding="utf-8")
        self.assertEqual(self.codes(), [(FAIL, "PLAN_SECTION")])
        path.unlink()
        self.assertEqual(self.codes(), [(FAIL, "PLAN_MISSING")])

    def test_outline_length_against_format(self):
        self.write_plan(points=[f"p{i}" for i in range(8)])  # 8 × 12 s = 96 s > 90 s
        self.assertEqual(self.codes(), [(WARN, "PLAN_OUTLINE_LENGTH")])
        long = self.new("Long one", fmt="long", seconds=600)
        self.write_plan(long, points=("a", "b", "c"))  # 3 × 90 s = 270 s < 300 s
        self.assertEqual(self.codes(long), [(WARN, "PLAN_OUTLINE_LENGTH")])
        self.write_plan(long, points=("a", "b", "c", "d", "e"))
        self.assertEqual(self.codes(long), [])

    def test_rules_from_config(self):
        rules = self.tmp / "config/rules.json"
        data = json.loads(rules.read_text(encoding="utf-8"))
        data["planning"]["seconds_per_outline_point"]["short"] = 30  # 4 × 30 = 120 s
        rules.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.write_plan()
        self.assertEqual(self.codes(), [(WARN, "PLAN_OUTLINE_LENGTH")])
        data["planning"]["max_videos_per_channel_per_day"] = 0
        rules.write_text(json.dumps(data), encoding="utf-8")
        self.ctx.config._cache.clear()
        self.assertIn("max_videos_per_channel_per_day", self.bad("plan", "check", "plan-test"))

    def test_malay_plan(self):
        ms = self.new("Rancangan", lang="ms", division="food-cooking")
        self.write_plan(ms, hook="Nasi lemak bermula di kampung nelayan.", keyword="sejarah nasi lemak",
                        points=("Cangkuk", "Asal-usul", "Penutup"))
        self.assertEqual(self.codes(ms), [])


class TestSetDate(Base):
    def test_updates_project_json_and_only_the_date_section(self):
        self.write_plan(when="2026-12-01")
        before = self.plan_file().read_text(encoding="utf-8")
        out = self.ok("plan", "set-date", "plan-test", "2026-12-24")
        self.assertIn("planned publish date - → 2026-12-24", out)
        after = self.plan_file().read_text(encoding="utf-8")
        self.assertEqual(after, before.replace("## Target publish date\n2026-12-01\n", "## Target publish date\n2026-12-24\n"))
        self.assertEqual(find_project(self.ctx, "plan-test").meta["planned_publish"], "2026-12-24")
        self.assertEqual(self.codes(), [])

    def test_today_invalid_and_no_section(self):
        from factory.core.files import today
        self.ok("plan", "set-date", "plan-test", "today")
        self.assertEqual(find_project(self.ctx, "plan-test").meta["planned_publish"], today())
        self.assertIn("Invalid date", self.bad("plan", "set-date", "plan-test", "2026-13-01"))
        path = self.plan_file()
        path.write_text("# Plan without date section\n", encoding="utf-8")
        self.assertIn("only project.json was updated", self.ok("plan", "set-date", "plan-test", "2026-12-25"))
        self.assertEqual(path.read_text(encoding="utf-8"), "# Plan without date section\n")

    def test_out_of_sync_and_invalid_stored_date(self):
        self.write_plan(when="2026-12-01")
        self.p.meta["planned_publish"] = "2026-12-05"
        self.p.save()
        self.assertEqual(self.codes(), [(WARN, "PLAN_DATE_SYNC")])
        self.p.meta["planned_publish"] = "soon"
        self.p.save()
        self.assertIn((FAIL, "PLAN_DATE"), self.codes())


class TestCalendar(Base):
    def setUp(self):
        super().setUp()
        self.write_plan(when="2026-12-01")  # dated via plan.md only
        self.a = self.new("Second en", division="gaming")
        self.b = self.new("Malay one", lang="ms", division="gaming")
        self.ok("plan", "set-date", self.a.id, "2026-12-03")
        self.ok("plan", "set-date", self.b.id, "2026-12-01")
        self.new("No date yet")

    def test_lists_all_dates_sorted_and_filters(self):
        out = self.ok("plan", "calendar")
        lines = [l for l in out.splitlines() if l.startswith("2026")]
        self.assertEqual([l.split()[0] for l in lines], ["2026-12-01", "2026-12-01", "2026-12-03"])
        self.assertNotIn("no-date-yet", out)
        self.assertNotIn("Malay", self.ok("plan", "calendar", "--lang", "en").replace("malay", "Malay"))
        self.assertEqual(self.ok("plan", "calendar", "--division", "gaming").count("2026-12"), 2)
        self.assertEqual(self.ok("plan", "calendar", "--from", "2026-12-02").count("2026-12"), 1)
        self.assertEqual(self.ok("plan", "calendar", "--to", "2026-12-01").count("2026-12"), 2)
        self.assertIn("invalid date", self.bad("plan", "calendar", "--from", "12/01/2026"))
        self.assertIn("No planned publish dates", self.ok("plan", "calendar", "--from", "2027-01-01"))

    def test_clashes_per_channel_per_day(self):
        self.assertNotIn("clash", self.ok("plan", "calendar"))  # EN and MS are different channels
        extra = [self.new(f"Extra {i}") for i in range(2)]
        for p in extra:
            self.ok("plan", "set-date", p.id, "2026-12-01")
        out = self.ok("plan", "calendar")
        self.assertEqual(out.count("⚠ clash"), 3)  # 3 English videos on 2026-12-01 (limit 2)
        self.assertIn("Warning: 3 videos planned for the English channel on 2026-12-01", out)
        self.assertIn((WARN, "PLAN_CLASH"), self.codes(extra[0]))
        self.assertNotIn((WARN, "PLAN_CLASH"), self.codes(self.b))  # Malay channel unaffected


class TestGate(Base):
    def setUp(self):
        super().setUp()
        tick_all(self.p.folder / "01_research/research.md")
        add_source(self.ctx, self.p)
        advance(self.ctx, self.p)

    def test_planning_gate(self):
        tick_all(self.plan_file())
        with self.assertRaises(FactoryError) as e:
            advance(self.ctx, self.p)
        self.assertIn("PLAN_HOOK", str(e.exception))
        self.write_plan()
        self.assertEqual(advance(self.ctx, self.p), "script")

    def test_force_is_recorded(self):
        advance(self.ctx, self.p, force=True)
        self.assertIn("PLAN_OUTLINE", self.p.meta["history"][-1]["forced_findings"])


class TestSamplesUnchanged(unittest.TestCase):
    def test_english_sample_plan_passes_and_checks_change_nothing(self):
        ctx = Context()
        octopus = find_project(ctx, "octopus")
        path = planning.plan_path(ctx, octopus)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(planning.check_plan(ctx, octopus), [])
        self.assertEqual(planning.planned_date(ctx, octopus), "2026-11-20")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertNotIn("planned_publish", octopus.meta)


if __name__ == "__main__":
    unittest.main()
