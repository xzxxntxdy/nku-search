import re
import unittest

from nku_search.crawl_plan import (
    COMMON_DENY_PATTERNS,
    MIN_HOMEWORK_PAGES,
    SECTION_BY_KEY,
    TOTAL_TARGET_PAGES,
    allowed_domains_for,
    crawl_plan_summary,
    section_budgets_for,
    section_for_url,
    seed_urls_for,
)


class CrawlPlanTest(unittest.TestCase):
    def test_default_plan_exceeds_homework_minimum(self):
        summary = crawl_plan_summary()
        self.assertGreaterEqual(TOTAL_TARGET_PAGES, MIN_HOMEWORK_PAGES)
        self.assertGreaterEqual(summary["target_pages"], 160000)
        self.assertGreaterEqual(summary["section_count"], 8)

    def test_section_selection_builds_seed_domain_and_budget(self):
        seeds = seed_urls_for(["news", "schools"])
        domains = allowed_domains_for(["news", "schools"])
        budgets = section_budgets_for(["news", "schools"], scale_factor=2)
        self.assertIn("https://news.nankai.edu.cn/", seeds)
        self.assertIn("news.nankai.edu.cn", domains)
        self.assertGreaterEqual(budgets["news"], 72000)

    def test_section_for_url_maps_topic(self):
        self.assertEqual(section_for_url("https://news.nankai.edu.cn/ywsd/index.htm").key, "news")
        self.assertEqual(section_for_url("https://cs.nankai.edu.cn/info/1001/1.htm").category, "院系学科")
        self.assertEqual(section_for_url("https://lib.nankai.edu.cn/main.htm").key, "library")
        self.assertEqual(section_for_url("http://12club.nankai.edu.cn/").key, "anime")

    def test_crawl_filters_dead_subdomains_and_large_binary_assets(self):
        deny_patterns = [re.compile(pattern) for pattern in COMMON_DENY_PATTERNS]
        blocked_urls = [
            "http://opac.lib.nankai.edu.cn/robots.txt",
            "http://ic.lib.nankai.edu.cn/robots.txt",
            "http://tech.math.nankai.edu.cn/robots.txt",
            "https://graduate.nankai.edu.cn/_upload/file/B.zip",
            "https://medical.nankai.edu.cn/_visitcount?siteId=113&type=2",
        ]
        for url in blocked_urls:
            self.assertTrue(any(pattern.search(url) for pattern in deny_patterns), url)

        self.assertFalse(any(pattern.search("https://lib.nankai.edu.cn/_upload/file/course.PPT") for pattern in deny_patterns))

        schools_allow = [re.compile(pattern) for pattern in SECTION_BY_KEY["schools"].include_patterns]
        self.assertTrue(any(pattern.search("https://math.nankai.edu.cn/index.htm") for pattern in schools_allow))
        self.assertTrue(any(pattern.search("http://news.math.nankai.edu.cn/index.htm") for pattern in schools_allow))

    def test_include_patterns_are_tuple_regexes(self):
        from nku_search.crawl_plan import CRAWL_SECTIONS

        for section in CRAWL_SECTIONS:
            self.assertIsInstance(section.include_patterns, tuple, section.key)
            self.assertTrue(section.include_patterns, section.key)
            for pattern in section.include_patterns:
                self.assertIsInstance(pattern, str, section.key)
                self.assertIn("nankai", pattern, section.key)

if __name__ == "__main__":
    unittest.main()
