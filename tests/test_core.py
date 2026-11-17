import unittest

from factory.core.files import slugify, unchecked_items
from factory.core.templates import find_template, render
from factory.modules.ideas import score
from tests.helpers import make_sandbox, remove_sandbox


class TestCore(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render("{{a}} {{ b }} {{c}}", {"a": 1, "b": "x"}), "1 x {{c}}")

    def test_slugify(self):
        self.assertEqual(slugify("Why Octopuses Have 3 Hearts?!"), "why-octopuses-have-3-hearts")
        self.assertEqual(slugify("Kenapa sotong ada 3 jantung"), "kenapa-sotong-ada-3-jantung")
        self.assertEqual(slugify("!!!"), "untitled")
        self.assertEqual(slugify("Café crème"), "cafe-creme")

    def test_unchecked_items(self):
        text = "- [ ] one\n- [x] two\n  * [ ] three\n- [X] four"
        self.assertEqual(unchecked_items(text), ["one", "three"])

    def test_score(self):
        self.assertEqual(score(5, 1, 1), 5.0)
        self.assertEqual(score(1, 5, 5), 1.0)
        self.assertEqual(score(4, 2, 2), 4.0)


class TestTemplateOverrides(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()

    def tearDown(self):
        remove_sandbox(self.tmp)

    def test_language_override_then_brand_override(self):
        p = self.ctx.paths
        self.assertEqual(find_template(p, "script.md", "qhaze", "en"), p.templates / "script.md")
        self.assertEqual(find_template(p, "script.md", "qhaze", "ms"), p.templates / "ms" / "script.md")
        brand_tpl = p.brand_dir("qhaze") / "templates" / "ms" / "script.md"
        brand_tpl.parent.mkdir(parents=True)
        brand_tpl.write_text("brand", encoding="utf-8")
        self.assertEqual(find_template(p, "script.md", "qhaze", "ms"), brand_tpl)


if __name__ == "__main__":
    unittest.main()
