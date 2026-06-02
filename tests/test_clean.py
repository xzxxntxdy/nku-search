import json
import tempfile
import unittest
from pathlib import Path

from nku_search.clean import clean_jsonl, filtered_outgoing_links, is_service_url
from nku_search.index import load_pages


def page(url, title="title", text="text", html="<html>text</html>", filetype="html", section="main", status=200, links=None):
    return {
        "url": url,
        "title": title,
        "text": text,
        "html": html,
        "anchors": [],
        "outgoing_links": links or [],
        "content_type": "text/html",
        "filetype": filetype,
        "section": section,
        "category": section,
        "fetched_at": "2026-05-25T00:00:00+00:00",
        "status": status,
    }


class CleanJsonlTest(unittest.TestCase):
    def test_service_url_detection(self):
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/_visitcount?siteId=1"))
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/search.jsp?q=test"))
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/search_result.jsp?q=test"))
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/wxy/Login.aspx?style=1"))
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/virexp/prepare_login"))
        self.assertTrue(is_service_url("https://x.nankai.edu.cn/login"))
        self.assertFalse(is_service_url("https://news.nankai.edu.cn/2026/0525/a.shtml"))

    def test_outgoing_links_are_deduped_and_filtered(self):
        links = filtered_outgoing_links(
            [
                "https://news.nankai.edu.cn/a.shtml?utm_source=x",
                "https://news.nankai.edu.cn/a.shtml",
                "https://news.nankai.edu.cn/_visitcount?siteId=1",
                "javascript:void(0)",
            ]
        )
        self.assertEqual(links, ["https://news.nankai.edu.cn/a.shtml?utm_source=x"])

    def test_clean_jsonl_drops_low_value_and_keeps_best_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "raw.jsonl"
            output_path = Path(tmp) / "clean.jsonl"
            report_path = Path(tmp) / "report.md"
            rows = [
                page("https://news.nankai.edu.cn/a.shtml", title="short", text="x"),
                page("https://news.nankai.edu.cn/a.shtml", title="long", text="x" * 20),
                page("https://news.nankai.edu.cn/_visitcount?siteId=1"),
                page("https://news.nankai.edu.cn/search.jsp?q=x"),
                page("https://news.nankai.edu.cn/empty.htm", title="", text="", html=""),
                page("https://news.nankai.edu.cn/file.pdf", title="file", text="", html="", filetype="pdf"),
            ]
            input_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            report = clean_jsonl(input_path, output_path, report_path)
            pages = load_pages(output_path)
            self.assertTrue(report_path.exists())

        self.assertEqual(report.input_lines, 6)
        self.assertEqual(report.output_lines, 2)
        self.assertEqual(report.dropped["service_url"], 2)
        self.assertEqual(report.dropped["empty_html_shell"], 1)
        self.assertEqual(report.dropped["duplicate_url"], 1)
        self.assertEqual(pages[0].title, "long")
        self.assertEqual(pages[1].filetype, "pdf")


if __name__ == "__main__":
    unittest.main()


