from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

from nku_search.config import DOCUMENT_EXTENSIONS, get_settings
from nku_search.crawl_plan import (
    allowed_domains_for,
    get_crawl_plan,
    section_for_url,
    seed_urls_for,
)
from nku_search.crawler_project.items import NkuPageItem
from nku_search.crawler_project.pipelines import existing_output_counts, existing_output_urls
from nku_search.frontier import canonicalize_frontier_url, is_low_value_list_page, select_frontier_links
from nku_search.models import utc_now_iso
from nku_search.text import extract_12club_resource_links, extract_asset_links, extract_document_text, extract_document_title, extract_links, html_to_text, infer_filetype


TWELVE_CLUB_CATEGORIES = ("anime", "comic", "game", "novel")
TWELVE_CLUB_RESOURCE_ACTION_RE = re.compile(
    r'"([0-9a-f]{40,})"[^;]{0,800}"?getPageResourceActions"?', re.IGNORECASE | re.DOTALL
)
INIT_TOTAL_RE = re.compile(r'initTotal\\?":\s*(\d+)', re.IGNORECASE)
PAGE_SIZE = 24
LOW_VALUE_RULE_DENY_PATTERNS = (
    r".*/(?:\d+/)?list\d*\.(?:htm|html|shtml|psp)(?:[?#].*)?$",
    r".*/_visitcount(?:[?#].*)?$",
    r".*/_wp3services/.*",
)


def _domain_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)


def _is_xml_response(filetype: str, content_type: str) -> bool:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    return filetype == "xml" or media_type in {"application/xml", "text/xml"} or media_type.endswith("+xml")


def _canonical_output_url(url: str) -> str:
    canonical = canonicalize_frontier_url(url)
    return canonical or url.strip()



class NkuCampusSpider(CrawlSpider):
    """Rule-driven campus crawler modeled after Scrapy's CrawlSpider project style."""

    name = "nku_campus"
    project_settings = get_settings()
    allowed_domains = list(project_settings.allowed_domains)
    start_urls = list(project_settings.seed_urls)
    rules: tuple[Rule, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_section_keys: tuple[str, ...] = ()
        self.section_budgets: dict[str, int] = {}
        self.section_counts: dict[str, int] = {}
        self.written_urls: set[str] = set()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.configure_from_settings(crawler.settings)
        spider.configure_budget_state(crawler)
        return spider

    def configure_from_settings(self, crawler_settings) -> None:
        configured = tuple(crawler_settings.getlist("NKU_CRAWL_SECTIONS") or ())
        selected_sections = get_crawl_plan(list(configured) or None)
        self.selected_section_keys = tuple(section.key for section in selected_sections)
        self.start_urls = list(crawler_settings.getlist("NKU_START_URLS") or seed_urls_for(self.selected_section_keys))
        self.allowed_domains = list(
            crawler_settings.getlist("NKU_ALLOWED_DOMAINS") or allowed_domains_for(self.selected_section_keys)
        )
        allow_patterns = [pattern for section in selected_sections for pattern in section.include_patterns]
        allow_patterns.extend(crawler_settings.getlist("NKU_EXTRA_ALLOW_PATTERNS") or ())
        deny_patterns = [pattern for section in selected_sections for pattern in section.deny_patterns]
        deny_patterns.extend(LOW_VALUE_RULE_DENY_PATTERNS)
        self.rules = (
            Rule(
                LinkExtractor(
                    allow=allow_patterns,
                    deny=deny_patterns,
                    allow_domains=self.allowed_domains,
                    deny_extensions=[],
                    canonicalize=True,
                    unique=True,
                ),
                callback="parse_page",
                follow=True,
            ),
        )
        self._compile_rules()

    def configure_budget_state(self, crawler) -> None:
        output_path = Path(crawler.settings.get("NKU_OUTPUT_PATH") or get_settings().crawl_output)
        _total, section_counts = existing_output_counts(output_path)
        self.section_counts = dict(section_counts)
        self.section_budgets = dict(crawler.settings.getdict("NKU_SECTION_BUDGETS", {}))
        self.written_urls = {_canonical_output_url(url) for url in existing_output_urls(output_path)}

    def _section_budget_exhausted(self, section_key: str) -> bool:
        budget = self.section_budgets.get(section_key)
        return budget is not None and self.section_counts.get(section_key, 0) >= budget

    def _reserve_section_slot(self, section_key: str) -> bool:
        if self._section_budget_exhausted(section_key):
            self.crawler.stats.inc_value(f"nku/section_skipped_before_item/{section_key}")
            return False
        self.section_counts[section_key] = self.section_counts.get(section_key, 0) + 1
        return True

    def _should_write_item(self, url: str, section_key: str) -> bool:
        canonical = _canonical_output_url(url)
        if canonical in self.written_urls:
            self.crawler.stats.inc_value("nku/item_skipped_existing_url")
            return False
        if not self._reserve_section_slot(section_key):
            return False
        self.written_urls.add(canonical)
        return True

    def parse_start_url(self, response):
        return self.parse_page(response)

    def parse_page(self, response):
        content_type = response.headers.get("Content-Type", b"").decode("latin1", errors="ignore")
        filetype = infer_filetype(response.url, content_type)
        depth = response.meta.get("depth", 0)
        section = section_for_url(response.url)

        if self._section_budget_exhausted(section.key):
            self.crawler.stats.inc_value(f"nku/section_response_skipped/{section.key}")
            return

        if filetype in DOCUMENT_EXTENSIONS:
            max_parse_bytes = self.crawler.settings.getint("NKU_MAX_DOCUMENT_PARSE_BYTES", 4 * 1024 * 1024)
            if "download_stopped" in response.flags:
                text = ""
                self.crawler.stats.inc_value("nku/document_parse_skipped_download_stopped")
            elif len(response.body) > max_parse_bytes:
                text = ""
                self.crawler.stats.inc_value("nku/document_parse_skipped_too_large")
            else:
                text = extract_document_text(response.body, filetype)
            content_disposition = response.headers.get("Content-Disposition", b"").decode("latin1", errors="ignore")
            title = extract_document_title(
                response.body,
                filetype,
                response.url,
                text=text,
                content_disposition=content_disposition,
                fallback_title=response.url.rsplit("/", 1)[-1],
            )
            if not self._should_write_item(response.url, section.key):
                return
            yield NkuPageItem(
                url=response.url,
                title=title,
                text=text,
                html="",
                anchors=[],
                outgoing_links=[],
                content_type=content_type,
                filetype=filetype,
                section=section.key,
                category=section.category,
                fetched_at=utc_now_iso(),
                status=response.status,
                depth=depth,
                source_spider=self.name,
            )
            return

        if _is_xml_response(filetype, content_type):
            xml_text = response.text if hasattr(response, "text") else response.body.decode("utf-8", errors="ignore")
            raw_links = [
                url for url in extract_links(xml_text, response.url) if _domain_allowed(url, tuple(self.allowed_domains))
            ]
            outgoing_links = list(select_frontier_links(raw_links, self.crawler.settings.getfloat("NKU_FRONTIER_MIN_SCORE", 0.45)))
            for request in self._follow_discovered_links(response, outgoing_links, source="sitemap"):
                yield request
            return

        if filetype == "html" or "text/html" in content_type:
            html = response.text
            title, text, anchors = html_to_text(html)
            raw_outgoing_links = [
                url for url in extract_links(html, response.url) if _domain_allowed(url, tuple(self.allowed_domains))
            ]
            all_outgoing_links = list(select_frontier_links(raw_outgoing_links, self.crawler.settings.getfloat("NKU_FRONTIER_MIN_SCORE", 0.45)))
            frontier_only = is_low_value_list_page(response.url) and not self.crawler.settings.getbool("NKU_INDEX_LIST_PAGES", False)
            if frontier_only:
                self.crawler.stats.inc_value("nku/frontier_only_list_pages")
            elif self._should_write_item(response.url, section.key):
                yield NkuPageItem(
                    url=response.url,
                    title=title,
                    text=text,
                    html=html,
                    anchors=anchors,
                    outgoing_links=all_outgoing_links,
                    content_type=content_type or "text/html",
                    filetype="html",
                    section=section.key,
                    category=section.category,
                    fetched_at=utc_now_iso(),
                    status=response.status,
                    depth=depth,
                    source_spider=self.name,
                )
            for request in self._follow_discovered_links(response, all_outgoing_links, source="embedded"):
                yield request
            for request in self._schedule_12club_resource_frontier(response, html):
                yield request
            return

    def _follow_discovered_links(self, response, links, source: str):
        count = 0
        allowed_domains = tuple(self.allowed_domains)
        for url in links:
            if url == response.url or not _domain_allowed(url, allowed_domains):
                continue
            target_section = section_for_url(url).key
            if self._section_budget_exhausted(target_section):
                self.crawler.stats.inc_value(f"nku/discovered_requests/skipped_budget/{target_section}")
                continue
            if is_low_value_list_page(url):
                self.crawler.stats.inc_value("nku/discovered_requests/skipped_list")
                continue
            count += 1
            yield scrapy.Request(
                url,
                callback=self.parse_page,
                dont_filter=False,
                meta={"nku_discovery_source": source},
            )
        if count:
            self.crawler.stats.inc_value(f"nku/discovered_requests/{source}", count)

    def _schedule_12club_resource_frontier(self, response, html: str):
        parsed = urlparse(response.url)
        if parsed.netloc.lower() != "12club.nankai.edu.cn":
            return
        if self._section_budget_exhausted("anime"):
            return
        path = parsed.path.strip("/")
        if path == "":
            for category in TWELVE_CLUB_CATEGORIES:
                yield scrapy.Request(urljoin(response.url, f"/{category}"), callback=self.parse_page, dont_filter=False)
            return
        if path not in TWELVE_CLUB_CATEGORIES:
            return

        total_match = INIT_TOTAL_RE.search(html or "")
        if not total_match:
            return
        total = int(total_match.group(1))
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        if total_pages <= 1:
            return

        self.crawler.stats.set_value(f"nku/12club_total/{path}", total)
        script_urls = [
            url for url in extract_asset_links(html, response.url, {"js"}) if "/_next/static/chunks/" in url
        ]
        for script_url in script_urls:
            yield scrapy.Request(
                script_url,
                callback=self.parse_12club_script,
                dont_filter=True,
                meta={
                    "nku_12club_category": path,
                    "nku_12club_total_pages": total_pages,
                    "nku_12club_category_url": response.url,
                },
            )

    def parse_12club_script(self, response):
        category = response.meta.get("nku_12club_category")
        category_url = response.meta.get("nku_12club_category_url")
        total_pages = int(response.meta.get("nku_12club_total_pages") or 1)
        action_ids = sorted(set(TWELVE_CLUB_RESOURCE_ACTION_RE.findall(response.text or "")))
        if not category or not category_url or not action_ids:
            return
        action_id = action_ids[0]
        self.crawler.stats.set_value("nku/12club_action_id", action_id)
        for page_number in range(2, total_pages + 1):
            payload = [
                {
                    "category": category,
                    "selectedType": "all",
                    "selectedLanguage": "all",
                    "selectedStatus": "all",
                    "sortField": "updated",
                    "sortOrder": "desc",
                    "page": page_number,
                    "limit": PAGE_SIZE,
                }
            ]
            yield scrapy.Request(
                category_url,
                method="POST",
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Accept": "text/x-component",
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Next-Action": action_id,
                    "Origin": "http://12club.nankai.edu.cn",
                    "Referer": category_url,
                },
                callback=self.parse_12club_action_page,
                dont_filter=False,
                meta={"nku_discovery_source": "12club_action", "nku_12club_page": page_number},
            )

    def parse_12club_action_page(self, response):
        raw_links = [
            url for url in extract_links(response.text, response.url) if _domain_allowed(url, tuple(self.allowed_domains))
        ]
        raw_links.extend(extract_12club_resource_links(response.text))
        outgoing_links = list(select_frontier_links(raw_links, self.crawler.settings.getfloat("NKU_FRONTIER_MIN_SCORE", 0.45)))
        self.crawler.stats.inc_value("nku/12club_action_pages")
        for request in self._follow_discovered_links(response, outgoing_links, source="12club_action"):
            yield request







