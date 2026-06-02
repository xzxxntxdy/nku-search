import json
import os
import tempfile
import unittest
from pathlib import Path

from nku_search.index import iter_pages, load_pages, resolve_input


def minimal_page(url):
    return {
        "url": url,
        "title": "title",
        "text": "text",
        "html": "",
        "anchors": [],
        "outgoing_links": [],
        "content_type": "text/html",
        "filetype": "html",
        "section": "main",
        "category": "main",
        "fetched_at": "2026-05-25T00:00:00+00:00",
        "status": 200,
    }


class IndexInputTest(unittest.TestCase):
    def test_iter_pages_streams_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            path.write_text(json.dumps(minimal_page("https://a.nankai.edu.cn/")) + "\n", encoding="utf-8")
            pages = list(iter_pages(path))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].url, "https://a.nankai.edu.cn/")

    def test_load_pages_missing_file_returns_empty(self):
        self.assertEqual(load_pages(Path("missing-file.jsonl")), [])

    def test_resolve_input_prefers_clean_crawl_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_clean = os.environ.get("NKU_CLEAN_CRAWL_OUTPUT")
            old_raw = os.environ.get("NKU_CRAWL_OUTPUT")
            clean = Path(tmp) / "clean.jsonl"
            raw = Path(tmp) / "raw.jsonl"
            clean.write_text("", encoding="utf-8")
            raw.write_text("", encoding="utf-8")
            os.environ["NKU_CLEAN_CRAWL_OUTPUT"] = str(clean)
            os.environ["NKU_CRAWL_OUTPUT"] = str(raw)
            try:
                self.assertEqual(resolve_input(None), clean)
            finally:
                if old_clean is None:
                    os.environ.pop("NKU_CLEAN_CRAWL_OUTPUT", None)
                else:
                    os.environ["NKU_CLEAN_CRAWL_OUTPUT"] = old_clean
                if old_raw is None:
                    os.environ.pop("NKU_CRAWL_OUTPUT", None)
                else:
                    os.environ["NKU_CRAWL_OUTPUT"] = old_raw


if __name__ == "__main__":
    unittest.main()
