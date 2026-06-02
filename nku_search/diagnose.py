from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile

from .auth import AuthService
from .config import SAMPLE_DOCUMENTS_PATH
from .index import load_pages
from .query import SearchQuery
from .search_engine import LocalSearchBackend, SearchBackend
from .storage import Storage


REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "elasticsearch",
    "scrapy",
    "bs4",
    "jieba",
    "lxml",
]


def module_status() -> list[tuple[str, bool]]:
    return [(name, importlib.util.find_spec(name) is not None) for name in REQUIRED_MODULES]


def run_diagnostics(sample_path: Path) -> int:
    exit_code = 0
    print(f"Python: {sys.version.split()[0]}")
    print("Dependencies:")
    for name, ok in module_status():
        print(f"  {'OK ' if ok else 'MISS'} {name}")
        if not ok:
            exit_code = 1

    pages = load_pages(sample_path)
    print(f"Sample documents: {len(pages)} from {sample_path}")
    backend = LocalSearchBackend(pages)
    hits, total = backend.search(SearchQuery(q="信息检索"))
    print(f"Local search smoke: total={total}, first={hits[0].title if hits else 'NONE'}")
    if total == 0:
        exit_code = 1

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        storage = Storage(Path(tmpdir) / "search.db")
        auth = AuthService(storage)
        ok, message = auth.register("demo", "demo1234", "信息检索 人工智能")
        print(f"SQLite/auth smoke: {'OK' if ok else 'FAIL'} {message}")
        if not ok:
            exit_code = 1

    es = SearchBackend()
    print(f"Elasticsearch ping: {'OK' if es.ping() else 'SKIP/FAIL'}")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether the project can run.")
    parser.add_argument("--sample", type=Path, default=SAMPLE_DOCUMENTS_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(run_diagnostics(args.sample))


if __name__ == "__main__":
    main()
