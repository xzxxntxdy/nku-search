from __future__ import annotations

import re
from urllib.parse import urlparse

from scrapy import signals
from scrapy.exceptions import IgnoreRequest, StopDownload

from nku_search.crawl_plan import COMMON_DENY_PATTERNS, section_for_url
from nku_search.crawler_project.pipelines import existing_output_counts
from nku_search.text import infer_filetype


class NkuUrlFilterMiddleware:
    """Drop low-value requests and stop oversized documents before body download.

    Scrapy is already asynchronous; the throughput bottleneck in this project is
    slow campus hosts and large binary documents. This middleware protects the
    reactor by filtering persisted JOBDIR requests before network I/O and by
    stopping oversized document downloads from response headers/streamed bytes.
    """

    def __init__(self, max_document_bytes: int, section_budgets: dict[str, int] | None = None, section_counts: dict[str, int] | None = None) -> None:
        self.max_document_bytes = max_document_bytes
        self.deny_patterns = tuple(re.compile(pattern) for pattern in COMMON_DENY_PATTERNS)
        self.section_budgets = dict(section_budgets or {})
        self.section_counts = dict(section_counts or {})

    @classmethod
    def from_crawler(cls, crawler):
        from pathlib import Path
        from nku_search.config import get_settings

        output_path = Path(crawler.settings.get("NKU_OUTPUT_PATH") or get_settings().crawl_output)
        _total, section_counts = existing_output_counts(output_path)
        instance = cls(
            crawler.settings.getint("NKU_MAX_DOCUMENT_DOWNLOAD_BYTES", 3 * 1024 * 1024),
            section_budgets=crawler.settings.getdict("NKU_SECTION_BUDGETS", {}),
            section_counts=section_counts,
        )
        crawler.signals.connect(instance.headers_received, signal=signals.headers_received)
        crawler.signals.connect(instance.bytes_received, signal=signals.bytes_received)
        return instance

    def process_request(self, request, spider):
        url = request.url
        if request.meta.get("dont_filter_nku"):
            return None
        if should_drop_url(url, self.deny_patterns):
            spider.crawler.stats.inc_value("nku/request_dropped_by_url_filter")
            raise IgnoreRequest(f"filtered low-value or broken URL: {url}")
        section = section_for_url(url).key
        budget = self.section_budgets.get(section)
        if budget is not None and self.section_counts.get(section, 0) >= budget:
            spider.crawler.stats.inc_value(f"nku/request_dropped_by_section_budget/{section}")
            raise IgnoreRequest(f"section {section} already reached budget {budget}: {url}")
        return None

    def headers_received(self, headers, body_length, request, spider):
        if not is_document_url(request.url):
            return None
        content_length = _content_length(headers, body_length)
        if content_length is not None and content_length > self.max_document_bytes:
            spider.crawler.stats.inc_value("nku/document_download_stopped_by_header")
            raise StopDownload(fail=False)
        return None

    def bytes_received(self, data, request, spider):
        if not is_document_url(request.url):
            return None
        received = int(request.meta.get("nku_document_bytes_received", 0)) + len(data)
        request.meta["nku_document_bytes_received"] = received
        if received > self.max_document_bytes:
            spider.crawler.stats.inc_value("nku/document_download_stopped_by_stream")
            raise StopDownload(fail=False)
        return None


def _content_length(headers, body_length) -> int | None:
    parsed_body_length = _int_or_none(body_length)
    if parsed_body_length is not None and parsed_body_length >= 0:
        return parsed_body_length

    values = headers.getlist("Content-Length") if hasattr(headers, "getlist") else []
    for value in values:
        parsed_header_length = _int_or_none(value)
        if parsed_header_length is not None and parsed_header_length >= 0:
            return parsed_header_length
    return None


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="ignore")
    if isinstance(value, str):
        value = value.strip()
        if not value or not value.lstrip("+-").isdigit():
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_document_url(url: str) -> bool:
    return infer_filetype(url, "") in {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"}


def should_drop_url(url: str, deny_patterns: tuple[re.Pattern[str], ...] | None = None) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    if parsed.scheme not in {"http", "https"}:
        return True
    host = parsed.netloc.lower()
    if host in {"opac.lib.nankai.edu.cn", "ic.lib.nankai.edu.cn", "tech.math.nankai.edu.cn"}:
        return True
    patterns = deny_patterns or tuple(re.compile(pattern) for pattern in COMMON_DENY_PATTERNS)
    return any(pattern.search(url) for pattern in patterns)
