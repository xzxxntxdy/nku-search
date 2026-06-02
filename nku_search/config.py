from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
CRAWL_DIR = DATA_DIR / "crawl"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
TEMPLATE_DIR = ROOT_DIR / "nku_search" / "templates"
STATIC_DIR = ROOT_DIR / "nku_search" / "static"
SAMPLE_DOCUMENTS_PATH = ROOT_DIR / "nku_search" / "fixtures" / "sample_documents.jsonl"


DEFAULT_SEED_URLS = (
    "https://www.nankai.edu.cn/",
    "https://news.nankai.edu.cn/",
    "https://cs.nankai.edu.cn/",
    "https://lib.nankai.edu.cn/",
    "https://yzb.nankai.edu.cn/",
    "https://jwc.nankai.edu.cn/",
    "http://12club.nankai.edu.cn/",
)

DEFAULT_ALLOWED_DOMAINS = (
    "nankai.edu.cn",
    "12club.nankai.edu.cn",
)

DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
}


@dataclass(frozen=True)
class Settings:
    elasticsearch_url: str = field(default_factory=lambda: os.getenv("NKU_ES_URL", "http://localhost:9200"))
    index_name: str = field(default_factory=lambda: os.getenv("NKU_ES_INDEX", "nku_pages"))
    sqlite_path: Path = field(default_factory=lambda: Path(os.getenv("NKU_DB_PATH", DATA_DIR / "search.db")))
    crawl_output: Path = field(default_factory=lambda: Path(os.getenv("NKU_CRAWL_OUTPUT", CRAWL_DIR / "pages.jsonl")))
    clean_crawl_output: Path = field(default_factory=lambda: Path(os.getenv("NKU_CLEAN_CRAWL_OUTPUT", CRAWL_DIR / "pages_160k_clean.jsonl")))
    snapshot_dir: Path = field(default_factory=lambda: Path(os.getenv("NKU_SNAPSHOT_DIR", SNAPSHOT_DIR)))
    seed_urls: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SEED_URLS)
    allowed_domains: tuple[str, ...] = field(default_factory=lambda: DEFAULT_ALLOWED_DOMAINS)
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 NKU-IR-HW4-SearchBot/0.1 (+student homework; polite crawl)"
    request_delay_seconds: float = 0.6
    max_pages: int = 100_000


def get_settings() -> Settings:
    return Settings()


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CRAWL_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)



