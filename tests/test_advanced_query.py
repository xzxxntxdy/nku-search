import unittest

from nku_search.advanced_query import parse_advanced_query


class AdvancedQueryTest(unittest.TestCase):
    def test_parses_operators_phrases_and_exclusions(self):
        parsed = parse_advanced_query('site:https://news.nankai.edu.cn/ filetype:pdf title:人工智能 "信息检索" -招生')
        self.assertEqual(parsed.site, "https://news.nankai.edu.cn/")
        self.assertEqual(parsed.filetype, "pdf")
        self.assertIn("信息检索", parsed.phrases)
        self.assertTrue(parsed.title_terms)
        self.assertTrue(parsed.excluded_terms)

    def test_parses_date_and_url_filters(self):
        parsed = parse_advanced_query("inurl:news after:2026-05-01 before:2026-06-01 论坛")
        self.assertEqual(parsed.url_terms, ["news"])
        self.assertEqual(parsed.after, "2026-05-01")
        self.assertEqual(parsed.before, "2026-06-01")
        self.assertTrue(parsed.terms)


if __name__ == "__main__":
    unittest.main()

