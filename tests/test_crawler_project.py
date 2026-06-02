import json
import logging
import tempfile
import unittest
from pathlib import Path

from scrapy.exceptions import CloseSpider, DropItem, IgnoreRequest

from nku_search.crawl import apply_crawler_settings, high_value_jobdir_for
from nku_search.crawler_project.items import NkuPageItem
from nku_search.crawler_project.logformatter import NkuLogFormatter
from nku_search.crawler_project.middlewares import NkuUrlFilterMiddleware, _content_length, should_drop_url
from nku_search.crawler_project.pipelines import PageLimitPipeline, SectionBudgetPipeline, existing_output_counts, existing_output_urls
from nku_search.crawler_project.spiders.nku_crawl import TWELVE_CLUB_RESOURCE_ACTION_RE, _is_xml_response
from nku_search.text import extract_12club_resource_links


class CrawlerProjectTest(unittest.TestCase):
    def test_item_declares_expected_fields(self):
        fields = set(NkuPageItem.fields)
        self.assertIn("url", fields)
        self.assertIn("anchors", fields)
        self.assertIn("outgoing_links", fields)
        self.assertIn("section", fields)
        self.assertIn("category", fields)

    def test_page_limit_pipeline_counts_items(self):
        pipeline = PageLimitPipeline(max_pages=2)
        self.assertEqual(pipeline.process_item({}, spider=None), {})
        self.assertEqual(pipeline.count, 1)

    def test_page_limit_pipeline_respects_resume_count(self):
        pipeline = PageLimitPipeline(max_pages=2, initial_count=2)
        with self.assertRaises(CloseSpider):
            pipeline.process_item({}, spider=None)

    def test_section_budget_pipeline_keeps_counts(self):
        pipeline = SectionBudgetPipeline({"news": 2})
        item = {"section": "news"}
        self.assertEqual(pipeline.process_item(item, spider=DummySpider()), item)
        self.assertEqual(pipeline.process_item(item, spider=DummySpider()), item)

    def test_existing_output_counts_jsonl_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"section": "news", "url": "https://news.nankai.edu.cn/a.shtml"}),
                        json.dumps({"section": "news", "url": "https://news.nankai.edu.cn/b.shtml"}),
                        json.dumps({"section": "schools", "url": "https://cs.nankai.edu.cn/"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            total, sections = existing_output_counts(path)
            urls = existing_output_urls(path)
        self.assertEqual(total, 3)
        self.assertEqual(sections["news"], 2)
        self.assertEqual(sections["schools"], 1)
        self.assertIn("https://news.nankai.edu.cn/a.shtml", urls)

    def test_high_value_jobdir_does_not_reuse_legacy_scrapy_jobdir(self):
        jobdir = high_value_jobdir_for(Path("data/crawl/pages_160k.jsonl"))
        self.assertIn("jobs", jobdir.parts)
        self.assertEqual(jobdir.name, "pages_160k-highvalue-frontier")
        self.assertNotEqual(jobdir.name, "scrapy-job")

    def test_crawler_settings_use_single_polite_production_policy(self):
        settings = DummySettings()
        selected = apply_crawler_settings(settings)
        self.assertEqual(selected["CONCURRENT_REQUESTS"], 128)
        self.assertEqual(settings.values["CONCURRENT_REQUESTS"], (128, "cmdline"))
        self.assertEqual(settings.values["CONCURRENT_REQUESTS_PER_DOMAIN"], (8, "cmdline"))
        self.assertEqual(settings.values["AUTOTHROTTLE_ENABLED"], (True, "cmdline"))
        self.assertEqual(settings.values["NKU_MAX_DOCUMENT_DOWNLOAD_BYTES"], (3 * 1024 * 1024, "cmdline"))
        self.assertFalse(selected["NKU_INDEX_LIST_PAGES"])

    def test_crawler_settings_support_necessary_runtime_overrides(self):
        settings = DummySettings()
        selected = apply_crawler_settings(
            settings,
            concurrency=256,
            per_domain_concurrency=24,
            reactor_threads=128,
            download_delay=0.0,
            frontier_min_score=0.7,
        )
        self.assertEqual(selected["CONCURRENT_REQUESTS"], 256)
        self.assertEqual(selected["CONCURRENT_REQUESTS_PER_DOMAIN"], 24)
        self.assertEqual(selected["REACTOR_THREADPOOL_MAXSIZE"], 128)
        self.assertEqual(selected["DOWNLOAD_DELAY"], 0.0)
        self.assertEqual(selected["NKU_FRONTIER_MIN_SCORE"], 0.7)

    def test_content_length_accepts_string_body_length_and_header(self):
        self.assertEqual(_content_length(DummyHeaders([b"4096"]), "unknown"), 4096)
        self.assertEqual(_content_length(DummyHeaders(["8192"]), None), 8192)
        self.assertEqual(_content_length(DummyHeaders([]), "-1"), None)

    def test_url_filter_drops_old_queue_low_value_urls(self):
        self.assertTrue(should_drop_url("http://opac.lib.nankai.edu.cn/opac/search_adv.php"))
        self.assertTrue(should_drop_url("https://graduate.nankai.edu.cn/_upload/file/archive.zip"))
        self.assertTrue(should_drop_url("https://medical.nankai.edu.cn/_visitcount?siteId=113&type=2"))
        self.assertFalse(should_drop_url("https://bs.nankai.edu.cn/_upload/file/course.PPTX"))
        self.assertFalse(should_drop_url("https://math.nankai.edu.cn/index.htm"))
        self.assertFalse(should_drop_url("https://news.math.nankai.edu.cn/index.htm"))

    def test_url_filter_drops_sections_that_already_reached_budget(self):
        middleware = NkuUrlFilterMiddleware(
            max_document_bytes=1024,
            section_budgets={"schools": 42000},
            section_counts={"schools": 42000},
        )
        with self.assertRaises(IgnoreRequest):
            middleware.process_request(DummyRequest("https://medical.nankai.edu.cn/6504/list89.psp"), DummySpider())

    def test_dropitem_log_formatter_omits_large_item_payload(self):
        item = {"url": "https://medical.nankai.edu.cn/6504/list89.psp", "outgoing_links": ["https://x"] * 100}
        formatted = NkuLogFormatter().dropped(
            item,
            DropItem("section schools reached budget 42000"),
            response=None,
            spider=None,
        )
        self.assertEqual(formatted["level"], logging.INFO)
        self.assertNotIn("item", formatted["args"])
        self.assertNotIn("outgoing_links", formatted["msg"])
        self.assertIn("url", formatted["args"])

    def test_office_openxml_content_type_is_not_xml_response(self):
        self.assertFalse(
            _is_xml_response(
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        self.assertFalse(
            _is_xml_response(
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        )
        self.assertTrue(_is_xml_response("xml", "application/xml"))
        self.assertTrue(_is_xml_response("html", "application/rss+xml"))

    def test_12club_next_action_regex_finds_resource_action(self):
        chunk = '(0,r.createServerReference)("7f6255ca76d22d5b0a1cd313c2ee2dac8ec4f08bc8",r.callServer,void 0,r.findSourceMapURL,"getPageResourceActions")'
        self.assertEqual(
            TWELVE_CLUB_RESOURCE_ACTION_RE.findall(chunk),
            ["7f6255ca76d22d5b0a1cd313c2ee2dac8ec4f08bc8"],
        )

    def test_12club_action_payload_extracts_detail_links(self):
        payload = '{"image":"http://12club.nankai.edu.cn/openlist/d/resource/anime/a424242/banner.avif","dbId":"a542203"}'
        self.assertEqual(
            extract_12club_resource_links(payload),
            [
                "http://12club.nankai.edu.cn/anime/a424242",
                "http://12club.nankai.edu.cn/anime/a542203",
            ],
        )


class DummyStats:
    def inc_value(self, *_args, **_kwargs):
        return None

    def set_value(self, *_args, **_kwargs):
        return None


class DummyCrawler:
    stats = DummyStats()


class DummySpider:
    crawler = DummyCrawler()


class DummySettings:
    def __init__(self):
        self.values = {}

    def set(self, key, value, priority=None):
        self.values[key] = (value, priority)


class DummyHeaders:
    def __init__(self, values):
        self.values = values

    def getlist(self, _name):
        return self.values


class DummyRequest:
    def __init__(self, url):
        self.url = url
        self.meta = {}


if __name__ == "__main__":
    unittest.main()

