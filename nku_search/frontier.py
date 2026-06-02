from __future__ import annotations

import json
import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse, urldefrag

from nku_search.crawl_plan import COMMON_DENY_PATTERNS
from nku_search.text import extract_12club_resource_links

WEBPLUS_ARTICLE_RE = re.compile(r"/\d{4}/\d{4}/c\d+a\d+/page\.htm", re.IGNORECASE)
SUDY_ARTICLE_RE = re.compile(r"/\d{4}/\d{2}/\d{2}/\d+\.s?html", re.IGNORECASE)
INFO_ARTICLE_RE = re.compile(r"/(?:info|content)/\d+/\d+\.(?:htm|html|shtml|psp)", re.IGNORECASE)
TWELVE_CLUB_DETAIL_RE = re.compile(r"/(?:anime|comic|game|novel)/[acgn]\d{3,}/?$", re.IGNORECASE)
TWELVE_CLUB_REFRESH_PATHS = {"/anime", "/comic", "/game", "/novel"}
LIST_PAGE_RE = re.compile(r"/(?:\d+/)?list\d*\.(?:htm|html|shtml|psp)$", re.IGNORECASE)
DOCUMENT_RE = re.compile(r"(?i).*\.(?:pdf|doc|docx|xls|xlsx|txt)(?:[?#].*)?$")
SERVICE_RE = re.compile(r"(?i)(?:/_visitcount|/_wp3services|/api/tracking|/search(?:\?|/)|/login|/logout|/admin|/wp-admin)")
DENY_PATTERNS = tuple(re.compile(pattern) for pattern in COMMON_DENY_PATTERNS)

FRONTIER_SCORES = {
    "blocked": 0.00,
    "service": 0.00,
    "list": 0.10,
    "section": 0.45,
    "home": 0.70,
    "sitemap": 0.75,
    "content": 0.65,
    "document": 0.90,
    "detail": 1.00,
}
DEFAULT_MIN_SCORE = 0.45


@dataclass(frozen=True, slots=True)
class FrontierCandidate:
    url: str
    kind: str
    score: float


def sitemap_seed_urls_for_domains(domains: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seeds: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        host = str(domain or "").strip().lower()
        if not host or "/" in host or ":" in host:
            continue
        for scheme in ("https", "http"):
            url = f"{scheme}://{host}/sitemap.xml"
            if url not in seen:
                seen.add(url)
                seeds.append(url)
    return tuple(seeds)


@lru_cache(maxsize=500_000)
def canonicalize_frontier_url(url: str) -> str:
    normalized = _normalize_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else parsed.netloc.lower()
    if parsed.port and not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)):
        host = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=False)
            if not key.lower().startswith(("utm_", "spm"))
        ),
        doseq=True,
    )
    return urlunparse((scheme, host, path, "", query, ""))


@lru_cache(maxsize=500_000)
def classify_frontier_url(url: str) -> str:
    canonical = canonicalize_frontier_url(url)
    if not canonical:
        return "blocked"
    if not _is_allowed_domain(canonical):
        return "blocked"
    if any(pattern.search(canonical) for pattern in DENY_PATTERNS):
        return "blocked"
    parsed = urlparse(canonical)
    path = parsed.path or "/"
    lowered = canonical.lower()
    if SERVICE_RE.search(lowered):
        return "service"
    if path.endswith(("/sitemap.xml", "/sitemap_index.xml")):
        return "sitemap"
    if DOCUMENT_RE.match(lowered):
        return "document"
    if WEBPLUS_ARTICLE_RE.search(path) or SUDY_ARTICLE_RE.search(path) or INFO_ARTICLE_RE.search(path) or TWELVE_CLUB_DETAIL_RE.search(path):
        return "detail"
    if LIST_PAGE_RE.search(path):
        return "list"
    if path in {"/", "/main.htm", "/index.htm", "/index.html", "/default.htm"}:
        return "home"
    if path.count("/") <= 2 and path.endswith((".htm", ".html", ".shtml", ".psp")):
        return "section"
    return "content"


def frontier_score(url: str) -> float:
    return FRONTIER_SCORES[classify_frontier_url(url)]


def is_low_value_list_page(url: str) -> bool:
    return classify_frontier_url(url) == "list"


def make_frontier_candidate(url: str) -> FrontierCandidate | None:
    canonical = canonicalize_frontier_url(url)
    if not canonical:
        return None
    kind = classify_frontier_url(canonical)
    return FrontierCandidate(canonical, kind, FRONTIER_SCORES[kind])


def select_frontier_links(urls: list[str] | tuple[str, ...], min_score: float = DEFAULT_MIN_SCORE) -> tuple[str, ...]:
    candidates: dict[str, FrontierCandidate] = {}
    for url in urls:
        candidate = make_frontier_candidate(str(url))
        if candidate is None or candidate.score < min_score or candidate.kind in {"blocked", "service", "list"}:
            continue
        candidates[candidate.url] = candidate
    ordered = sorted(candidates.values(), key=lambda item: (-item.score, urlparse(item.url).netloc, item.url))
    return tuple(item.url for item in ordered)


def build_expanded_frontier(
    output_path: Path,
    max_extra_urls: int = 180_000,
    min_score: float = DEFAULT_MIN_SCORE,
) -> tuple[str, ...]:
    """Build a high-value resume frontier from previously crawled JSONL.

    The policy follows the same shape as mature frontier crawlers: canonicalize,
    score, deduplicate, and only schedule URLs that are likely to produce search
    documents. Synthetic listN pages are intentionally not generated.
    """

    if not output_path.exists():
        return ()

    written_urls: set[str] = set()
    refresh_urls: set[str] = set()
    candidates: dict[str, FrontierCandidate] = {}
    with output_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            page_url = canonicalize_frontier_url(str(item.get("url") or ""))
            if page_url:
                written_urls.add(page_url)
                if _is_12club_refresh_url(page_url):
                    refresh_urls.add(page_url)
            links = list(item.get("outgoing_links") or [])
            if "12club.nankai.edu.cn" in page_url:
                links.extend(extract_12club_resource_links(str(item.get("html") or "")))
            for link in links:
                candidate = make_frontier_candidate(str(link))
                if candidate is None or candidate.url in candidates:
                    continue
                if candidate.score < min_score or candidate.kind in {"blocked", "service", "list"}:
                    continue
                candidates[candidate.url] = candidate

    for url in refresh_urls:
        candidate = make_frontier_candidate(url)
        if candidate is not None and candidate.score >= min_score:
            candidates[url] = candidate
    for url in written_urls - refresh_urls:
        candidates.pop(url, None)
    ordered = sorted(candidates.values(), key=lambda item: (-item.score, urlparse(item.url).netloc, item.url))
    return tuple(item.url for item in ordered[: max(0, int(max_extra_urls))])


def _is_12club_refresh_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() == "12club.nankai.edu.cn" and parsed.path.rstrip("/") in TWELVE_CLUB_REFRESH_PATHS


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        url = urldefrag(url.strip())[0]
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _is_allowed_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("nankai.edu.cn") or host == "12club.nankai.edu.cn"



