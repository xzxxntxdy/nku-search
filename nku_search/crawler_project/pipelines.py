from __future__ import annotations

import json
from pathlib import Path

from scrapy.exceptions import CloseSpider, DropItem

from nku_search.config import ensure_data_dirs, get_settings
from nku_search.models import CrawledPage, utc_now_iso


_OUTPUT_COUNT_CACHE: dict[Path, tuple[int, dict[str, int]]] = {}
_OUTPUT_URL_CACHE: dict[Path, set[str]] = {}


def _cache_key(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def existing_output_counts(output_path: Path) -> tuple[int, dict[str, int]]:
    """Return existing JSONL total and per-section counts for resume-aware budgets."""

    key = _cache_key(output_path)
    if key in _OUTPUT_COUNT_CACHE:
        total, counts = _OUTPUT_COUNT_CACHE[key]
        return total, dict(counts)

    total = 0
    counts: dict[str, int] = {}
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                total += 1
                try:
                    section = str(json.loads(line).get("section") or "unknown")
                except json.JSONDecodeError:
                    section = "unknown"
                counts[section] = counts.get(section, 0) + 1

    _OUTPUT_COUNT_CACHE[key] = (total, dict(counts))
    return total, counts


def existing_output_urls(output_path: Path) -> set[str]:
    """Return URLs already present in the JSONL output for resume de-duplication."""

    key = _cache_key(output_path)
    if key in _OUTPUT_URL_CACHE:
        return set(_OUTPUT_URL_CACHE[key])

    urls: set[str] = set()
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    url = str(json.loads(line).get("url") or "")
                except json.JSONDecodeError:
                    continue
                if url:
                    urls.add(url)

    _OUTPUT_URL_CACHE[key] = set(urls)
    return urls


def configured_output_path(crawler) -> Path:
    configured = crawler.settings.get("NKU_OUTPUT_PATH")
    return Path(configured) if configured else get_settings().crawl_output


class PageLimitPipeline:
    """Close the spider once the cumulative written-page budget is reached."""

    def __init__(self, max_pages: int, initial_count: int = 0) -> None:
        self.max_pages = max_pages
        self.count = initial_count

    @classmethod
    def from_crawler(cls, crawler):
        output_path = configured_output_path(crawler)
        initial_count, _section_counts = existing_output_counts(output_path)
        return cls(int(crawler.settings.getint("NKU_MAX_PAGES", get_settings().max_pages)), initial_count)

    def process_item(self, item, spider):
        if self.count >= self.max_pages:
            raise CloseSpider(f"reached NKU_MAX_PAGES={self.max_pages}")
        self.count += 1
        if spider is not None:
            spider.crawler.stats.set_value("nku/page_limit_count", self.count)
        return item


class SectionBudgetPipeline:
    """Keep a cumulative written-page budget for every configured crawl section."""

    def __init__(self, budgets: dict[str, int], initial_counts: dict[str, int] | None = None) -> None:
        self.budgets = budgets
        self.counts: dict[str, int] = dict(initial_counts or {})

    @classmethod
    def from_crawler(cls, crawler):
        output_path = configured_output_path(crawler)
        _total, section_counts = existing_output_counts(output_path)
        return cls(dict(crawler.settings.getdict("NKU_SECTION_BUDGETS", {})), section_counts)

    def process_item(self, item, spider):
        section = str(item.get("section") or "unknown")
        budget = self.budgets.get(section)
        current = self.counts.get(section, 0)
        if budget is not None and current >= budget:
            spider.crawler.stats.inc_value(f"nku/section_dropped/{section}")
            raise DropItem(f"section {section} reached budget {budget}")
        self.counts[section] = current + 1
        spider.crawler.stats.set_value(f"nku/section_count/{section}", self.counts[section])
        return item


class JsonlWriterPipeline:
    """Write normalized crawl items to the JSONL format consumed by the indexer."""

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.file = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(configured_output_path(crawler))

    def open_spider(self, spider) -> None:
        ensure_data_dirs()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.output_path.open("a", encoding="utf-8")

    def close_spider(self, spider) -> None:
        if self.file:
            self.file.close()

    def process_item(self, item, spider):
        page = CrawledPage(
            url=str(item.get("url", "")),
            title=str(item.get("title", "")),
            text=str(item.get("text", "")),
            html=str(item.get("html", "")),
            anchors=list(item.get("anchors", [])),
            outgoing_links=list(item.get("outgoing_links", [])),
            content_type=str(item.get("content_type", "text/html")),
            filetype=str(item.get("filetype", "html")),
            section=str(item.get("section", "main")),
            category=str(item.get("category", "main")),
            fetched_at=str(item.get("fetched_at", "")) or utc_now_iso(),
            status=int(item.get("status", 200)),
        )
        assert self.file is not None
        self.file.write(page.to_json_line() + "\n")
        self.file.flush()
        spider.crawler.stats.inc_value("nku/items_written")
        return item
