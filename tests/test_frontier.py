import json
import tempfile
import unittest
from pathlib import Path

from nku_search.frontier import (
    build_expanded_frontier,
    canonicalize_frontier_url,
    classify_frontier_url,
    frontier_score,
    is_low_value_list_page,
    select_frontier_links,
    sitemap_seed_urls_for_domains,
)


class FrontierExpansionTest(unittest.TestCase):
    def test_canonicalizes_and_scores_frontier_urls(self):
        url = canonicalize_frontier_url("HTTPS://CS.NANKAI.EDU.CN:443/2025/0522/c17471a596037/page.htm?utm_source=x&b=2")
        self.assertEqual(url, "https://cs.nankai.edu.cn/2025/0522/c17471a596037/page.htm?b=2")
        self.assertEqual(classify_frontier_url(url), "detail")
        self.assertGreater(frontier_score(url), frontier_score("https://cs.nankai.edu.cn/17471/list2.htm"))

    def test_rejects_low_value_list_and_service_urls(self):
        urls = select_frontier_links(
            (
                "https://medical.nankai.edu.cn/6504/list89.psp",
                "https://medical.nankai.edu.cn/_visitcount?siteId=113&type=2&columnId=6504",
                "https://medical.nankai.edu.cn/2025/0522/c17471a596037/page.htm",
                "https://medical.nankai.edu.cn/_upload/article/files/a.pdf",
            )
        )
        self.assertNotIn("https://medical.nankai.edu.cn/6504/list89.psp", urls)
        self.assertFalse(any("_visitcount" in url for url in urls))
        self.assertIn("https://medical.nankai.edu.cn/2025/0522/c17471a596037/page.htm", urls)
        self.assertIn("https://medical.nankai.edu.cn/_upload/article/files/a.pdf", urls)
        self.assertTrue(is_low_value_list_page("https://medical.nankai.edu.cn/6504/list89.psp"))

    def test_expanded_frontier_uses_only_high_value_real_outlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "url": "https://medical.nankai.edu.cn/index.htm",
                        "outgoing_links": [
                            "https://medical.nankai.edu.cn/6504/list89.psp",
                            "https://medical.nankai.edu.cn/_visitcount?siteId=113",
                            "https://medical.nankai.edu.cn/2025/0522/c17471a596037/page.htm",
                            "https://medical.nankai.edu.cn/_upload/article/files/a.pdf",
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            urls = build_expanded_frontier(path)
        self.assertEqual(
            urls,
            (
                "https://medical.nankai.edu.cn/2025/0522/c17471a596037/page.htm",
                "https://medical.nankai.edu.cn/_upload/article/files/a.pdf",
            ),
        )

    def test_expanded_frontier_adds_12club_detail_ids_from_saved_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "url": "http://12club.nankai.edu.cn/anime",
                        "outgoing_links": [],
                        "html": '<img src="/openlist/d/resource/anime/a424242/banner.avif"><script>{"dbId":"a542203"}</script>',
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            urls = build_expanded_frontier(path)
        self.assertIn("http://12club.nankai.edu.cn/anime/a424242", urls)
        self.assertIn("http://12club.nankai.edu.cn/anime/a542203", urls)

    def test_sitemap_seed_urls_cover_all_configured_domains(self):
        seeds = sitemap_seed_urls_for_domains(("news.nankai.edu.cn", "12club.nankai.edu.cn"))
        self.assertIn("https://news.nankai.edu.cn/sitemap.xml", seeds)
        self.assertIn("http://12club.nankai.edu.cn/sitemap.xml", seeds)


if __name__ == "__main__":
    unittest.main()

