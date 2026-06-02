from __future__ import annotations

import argparse
from pathlib import Path

from .config import CRAWL_DIR, ensure_data_dirs, get_settings
from .crawl_plan import (
    allowed_domains_for,
    crawl_plan_summary,
    format_plan_table,
    section_budgets_for,
    seed_urls_for,
)
from .frontier import build_expanded_frontier, sitemap_seed_urls_for_domains


CRAWLER_SETTINGS = {
    "CONCURRENT_REQUESTS": 128,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
    "DOWNLOAD_DELAY": 0.05,
    "DOWNLOAD_TIMEOUT": 12,
    "DOWNLOAD_MAXSIZE": 16 * 1024 * 1024,
    "DOWNLOAD_WARNSIZE": 16 * 1024 * 1024,
    "DNS_TIMEOUT": 5,
    "DNSCACHE_ENABLED": True,
    "DNSCACHE_SIZE": 100_000,
    "RETRY_TIMES": 1,
    "REACTOR_THREADPOOL_MAXSIZE": 64,
    "AUTOTHROTTLE_ENABLED": True,
    "AUTOTHROTTLE_START_DELAY": 0.05,
    "AUTOTHROTTLE_MAX_DELAY": 2.0,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 8.0,
    "NKU_MAX_DOCUMENT_DOWNLOAD_BYTES": 3 * 1024 * 1024,
    "NKU_MAX_DOCUMENT_PARSE_BYTES": 1 * 1024 * 1024,
    "NKU_FRONTIER_MIN_SCORE": 0.45,
    "NKU_INDEX_LIST_PAGES": False,
}


def high_value_jobdir_for(output_path: Path) -> Path:
    """Use a clean scheduler namespace so old low-value queues are never resumed."""

    try:
        stem = output_path.resolve().stem
    except OSError:
        stem = output_path.stem
    return CRAWL_DIR / "jobs" / f"{stem}-highvalue-frontier"


def apply_crawler_settings(
    scrapy_settings,
    concurrency: int | None = None,
    per_domain_concurrency: int | None = None,
    reactor_threads: int | None = None,
    download_delay: float | None = None,
    frontier_min_score: float | None = None,
) -> dict[str, object]:
    selected = dict(CRAWLER_SETTINGS)
    if concurrency is not None:
        selected["CONCURRENT_REQUESTS"] = concurrency
    if per_domain_concurrency is not None:
        selected["CONCURRENT_REQUESTS_PER_DOMAIN"] = per_domain_concurrency
    if reactor_threads is not None:
        selected["REACTOR_THREADPOOL_MAXSIZE"] = reactor_threads
    if download_delay is not None:
        selected["DOWNLOAD_DELAY"] = download_delay
    if frontier_min_score is not None:
        selected["NKU_FRONTIER_MIN_SCORE"] = frontier_min_score

    for key, value in selected.items():
        scrapy_settings.set(key, value, priority="cmdline")
    return selected


def run_crawler(
    max_pages: int | None = None,
    output: Path | None = None,
    sections: list[str] | None = None,
    scale_factor: float = 1.0,
    concurrency: int | None = None,
    per_domain_concurrency: int | None = None,
    reactor_threads: int | None = None,
    download_delay: float | None = None,
    expand_frontier: bool = False,
    frontier_max_extra: int = 180_000,
    frontier_min_score: float = 0.45,
    jobdir: Path | None = None,
) -> None:
    try:
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings
    except Exception as exc:
        raise RuntimeError("Scrapy is required for crawling. Run: pip install -r requirements.txt") from exc

    settings = get_settings()
    ensure_data_dirs()
    summary = crawl_plan_summary(sections, scale_factor=scale_factor)
    effective_max_pages = max_pages or int(summary["target_pages"]) or settings.max_pages
    output_path = output or settings.crawl_output
    jobdir_path = jobdir or high_value_jobdir_for(output_path)
    jobdir_path.parent.mkdir(parents=True, exist_ok=True)

    scrapy_settings = get_project_settings()
    applied_settings = apply_crawler_settings(
        scrapy_settings,
        concurrency=concurrency,
        per_domain_concurrency=per_domain_concurrency,
        reactor_threads=reactor_threads,
        download_delay=download_delay,
        frontier_min_score=frontier_min_score,
    )

    base_start_urls = list(seed_urls_for(sections))
    base_allowed_domains = list(allowed_domains_for(sections))
    extra_start_urls: tuple[str, ...] = ()
    if expand_frontier:
        extra_start_urls = build_expanded_frontier(
            output_path,
            max_extra_urls=frontier_max_extra,
            min_score=frontier_min_score,
        )
        print(f"Expanded high-value frontier: {len(extra_start_urls)} extra seed URLs from {output_path}")

    for url in extra_start_urls:
        try:
            from urllib.parse import urlparse

            host = urlparse(url).netloc.lower()
        except ValueError:
            continue
        if host.endswith("nankai.edu.cn") and "nankai.edu.cn" not in base_allowed_domains:
            base_allowed_domains.append("nankai.edu.cn")
        elif host == "12club.nankai.edu.cn" and host not in base_allowed_domains:
            base_allowed_domains.append(host)

    sitemap_start_urls = list(sitemap_seed_urls_for_domains(tuple(base_allowed_domains)))
    start_urls = tuple(dict.fromkeys([*base_start_urls, *sitemap_start_urls, *extra_start_urls]))

    scrapy_settings.set("NKU_MAX_PAGES", effective_max_pages, priority="cmdline")
    scrapy_settings.set("NKU_OUTPUT_PATH", str(output_path), priority="cmdline")
    scrapy_settings.set("NKU_CRAWL_SECTIONS", tuple(sections or ()), priority="cmdline")
    scrapy_settings.set("NKU_CRAWL_SCALE_FACTOR", scale_factor, priority="cmdline")
    scrapy_settings.set("NKU_SECTION_BUDGETS", section_budgets_for(sections, scale_factor=scale_factor), priority="cmdline")
    scrapy_settings.set("NKU_START_URLS", start_urls, priority="cmdline")
    scrapy_settings.set("NKU_ALLOWED_DOMAINS", tuple(dict.fromkeys(base_allowed_domains)), priority="cmdline")
    scrapy_settings.set("JOBDIR", str(jobdir_path), priority="cmdline")
    if expand_frontier:
        scrapy_settings.set(
            "NKU_EXTRA_ALLOW_PATTERNS",
            (r"https?://[^/]+\.nankai\.edu\.cn/.*", r"https?://nankai\.edu\.cn/.*", r"https?://12club\.nankai\.edu\.cn/.*"),
            priority="cmdline",
        )

    from .crawler_project.spiders.nku_crawl import NkuCampusSpider

    print(format_plan_table(sections, scale_factor=scale_factor))
    print("Crawler settings: " + ", ".join(f"{key}={value}" for key, value in applied_settings.items()))
    print(f"Output: {output_path}")
    print(f"Scheduler JOBDIR: {jobdir_path}")
    process = CrawlerProcess(scrapy_settings)
    process.crawl(NkuCampusSpider)
    process.start()


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Focused high-value crawler for NKU campus resources.")
    parser.add_argument("--max-pages", type=int, default=None, help="Global close limit. Defaults to the selected section budget.")
    parser.add_argument("--output", type=Path, default=settings.crawl_output)
    parser.add_argument("--section", action="append", default=None, help="Run one section key. Repeat for multiple sections.")
    parser.add_argument("--scale-factor", type=float, default=1.0, help="Multiply every section budget for larger crawls.")
    parser.add_argument("--concurrency", type=int, default=None, help="Override global Scrapy concurrency.")
    parser.add_argument("--per-domain-concurrency", type=int, default=None, help="Override per-domain Scrapy concurrency.")
    parser.add_argument("--reactor-threads", type=int, default=None, help="Override Twisted reactor thread pool size.")
    parser.add_argument("--download-delay", type=float, default=None, help="Override per-slot download delay in seconds.")
    parser.add_argument("--expand-frontier", action="store_true", help="Use existing JSONL to seed high-value discovered NKU links only.")
    parser.add_argument("--frontier-max-extra", type=int, default=180000, help="Maximum expanded frontier URLs to add.")
    parser.add_argument("--frontier-min-score", type=float, default=0.45, help="Minimum frontier quality score for expanded/discovered links.")
    parser.add_argument("--jobdir", type=Path, default=None, help="Scheduler state directory. Defaults to a clean high-value queue per output file.")
    parser.add_argument("--list-sections", action="store_true", help="Print the large-scale crawl plan and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_sections:
        print(format_plan_table(args.section, scale_factor=args.scale_factor))
        return
    run_crawler(
        max_pages=args.max_pages,
        output=args.output,
        sections=args.section,
        scale_factor=args.scale_factor,
        concurrency=args.concurrency,
        per_domain_concurrency=args.per_domain_concurrency,
        reactor_threads=args.reactor_threads,
        download_delay=args.download_delay,
        expand_frontier=args.expand_frontier,
        frontier_max_extra=args.frontier_max_extra,
        frontier_min_score=args.frontier_min_score,
        jobdir=args.jobdir,
    )


if __name__ == "__main__":
    main()