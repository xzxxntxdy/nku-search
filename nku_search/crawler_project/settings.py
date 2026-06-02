from __future__ import annotations

from nku_search.config import CRAWL_DIR, get_settings


settings = get_settings()

BOT_NAME = "nku_search"
SPIDER_MODULES = ["nku_search.crawler_project.spiders"]
NEWSPIDER_MODULE = "nku_search.crawler_project.spiders"

ROBOTSTXT_OBEY = True
USER_AGENT = settings.user_agent
LOG_LEVEL = "INFO"
LOG_FORMATTER = "nku_search.crawler_project.logformatter.NkuLogFormatter"

CONCURRENT_REQUESTS = 128
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_DELAY = 0.05
DOWNLOAD_TIMEOUT = 12
DOWNLOAD_MAXSIZE = 16 * 1024 * 1024
DOWNLOAD_WARNSIZE = 16 * 1024 * 1024
DNS_TIMEOUT = 5
DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 100_000
RETRY_TIMES = 1
REACTOR_THREADPOOL_MAXSIZE = 64

NKU_MAX_DOCUMENT_DOWNLOAD_BYTES = 3 * 1024 * 1024
NKU_MAX_DOCUMENT_PARSE_BYTES = 1 * 1024 * 1024
NKU_FRONTIER_MIN_SCORE = 0.45
NKU_INDEX_LIST_PAGES = False

DEPTH_PRIORITY = 1
SCHEDULER_DISK_QUEUE = "scrapy.squeues.PickleFifoDiskQueue"
SCHEDULER_MEMORY_QUEUE = "scrapy.squeues.FifoMemoryQueue"

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.05
AUTOTHROTTLE_MAX_DELAY = 2.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 8.0

HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400
HTTPCACHE_DIR = str(CRAWL_DIR / "httpcache")
JOBDIR = str(CRAWL_DIR / "scrapy-job")

DOWNLOADER_MIDDLEWARES = {
    "nku_search.crawler_project.middlewares.NkuUrlFilterMiddleware": 50,
}

ITEM_PIPELINES = {
    "nku_search.crawler_project.pipelines.SectionBudgetPipeline": 100,
    "nku_search.crawler_project.pipelines.PageLimitPipeline": 200,
    "nku_search.crawler_project.pipelines.JsonlWriterPipeline": 300,
}

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"