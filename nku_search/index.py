from __future__ import annotations

import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
import time
from typing import Iterable, Iterator

from .config import SAMPLE_DOCUMENTS_PATH, ensure_data_dirs, get_settings
from .models import CrawledPage, utc_now_iso
from .ranking import compute_pagerank
from .recommend import extract_suggestion_terms
from .search_engine import SearchBackend
from .storage import Storage


PAGERANK_LINK_LIMIT = 64
SUGGESTION_LIMIT = 20_000
INDEX_CHUNK_SIZE = 500
INDEX_PROGRESS_EVERY = 1_000
SCAN_PROGRESS_EVERY = 10_000
MAX_INDEXED_LINK_LENGTH = 2048


def iter_pages(path: Path) -> Iterator[CrawledPage]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                yield CrawledPage.from_dict(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}") from exc


def load_pages(path: Path) -> list[CrawledPage]:
    return list(iter_pages(path))


def dedupe_pages(pages: Iterable[CrawledPage]) -> list[CrawledPage]:
    seen: dict[str, CrawledPage] = {}
    for page in pages:
        if page.url:
            seen[page.url] = page
    return list(seen.values())


def save_snapshot(page: CrawledPage, snapshot_dir: Path) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{page.doc_id}.html"
    if path.exists():
        return
    if page.html:
        path.write_text(page.html, encoding="utf-8")
        return
    path.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>{escape(page.title)}</title>
<pre>{escape(page.text)}</pre>
""",
        encoding="utf-8",
    )


def save_snapshots(pages: Iterable[CrawledPage], snapshot_dir: Path) -> None:
    for page in pages:
        save_snapshot(page, snapshot_dir)


def collect_url_map(path: Path) -> tuple[dict[str, str], int]:
    url_to_doc_id: dict[str, str] = {}
    scanned = 0
    for page in iter_pages(path):
        scanned += 1
        if page.url and page.url not in url_to_doc_id:
            url_to_doc_id[page.url] = page.doc_id
        if scanned % SCAN_PROGRESS_EVERY == 0:
            print(f"Scanned {scanned} lines, unique URLs {len(url_to_doc_id)}", flush=True)
    return url_to_doc_id, scanned


def _pagerank_targets(page: CrawledPage, url_to_doc_id: dict[str, str]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for url in page.outgoing_links:
        target = url_to_doc_id.get(url)
        if not target or target == page.doc_id or target in seen:
            continue
        targets.append(target)
        seen.add(target)
        if len(targets) >= PAGERANK_LINK_LIMIT:
            break
    return targets


def build_graph(path: Path, url_to_doc_id: dict[str, str]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    seen_urls: set[str] = set()
    scanned = 0
    for page in iter_pages(path):
        scanned += 1
        if not page.url or page.url in seen_urls:
            continue
        seen_urls.add(page.url)
        graph[page.doc_id] = _pagerank_targets(page, url_to_doc_id)
        if scanned % SCAN_PROGRESS_EVERY == 0:
            print(f"Built PageRank graph for {len(graph)} pages", flush=True)
    return graph


def _indexed_outgoing_links(links: Iterable[object]) -> list[str]:
    filtered: list[str] = []
    for raw_link in links:
        link = str(raw_link).strip()
        lower = link.lower()
        if not lower.startswith(("http://", "https://")):
            continue
        if len(link) > MAX_INDEXED_LINK_LENGTH or "base64," in lower or any(ch in link for ch in "\r\n\t"):
            continue
        filtered.append(link)
        if len(filtered) >= PAGERANK_LINK_LIMIT:
            break
    return filtered


def _index_document(page: CrawledPage, pagerank: dict[str, float]) -> dict[str, object]:
    document = page.to_index_document(pagerank.get(page.doc_id, 0.0))
    document["outgoing_links"] = _indexed_outgoing_links(document.get("outgoing_links", []))
    document["anchors"] = [str(anchor)[:512] for anchor in list(document.get("anchors", []))[:128]]
    return document


def stream_index_documents(
    path: Path,
    pagerank: dict[str, float],
    snapshot_dir: Path,
    suggestions: Counter[str],
) -> Iterator[dict[str, object]]:
    seen_urls: set[str] = set()
    emitted = 0
    for page in iter_pages(path):
        if not page.url or page.url in seen_urls:
            continue
        seen_urls.add(page.url)
        save_snapshot(page, snapshot_dir)
        for term, weight in extract_suggestion_terms(page.title, page.text):
            suggestions[term] += weight
        emitted += 1
        if emitted % SCAN_PROGRESS_EVERY == 0:
            print(f"Prepared {emitted} documents for Elasticsearch", flush=True)
        yield _index_document(page, pagerank)


def flush_suggestions(storage: Storage, suggestions: Counter[str]) -> int:
    rows = [
        (term, float(weight), "index", utc_now_iso())
        for term, weight in suggestions.most_common(SUGGESTION_LIMIT)
        if term.strip()
    ]
    if not rows:
        return 0
    with storage.connect() as connection:
        connection.executemany(
            """
            INSERT INTO suggestions(term, weight, source, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                weight = suggestions.weight + excluded.weight,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def _require_backend() -> SearchBackend:
    settings = get_settings()
    backend = SearchBackend(settings.elasticsearch_url, settings.index_name)
    if not backend.ping():
        raise RuntimeError("Elasticsearch is not reachable. Start it with: docker compose up -d elasticsearch")
    return backend


def index_pages(pages: list[CrawledPage], reset: bool = False) -> int:
    settings = get_settings()
    storage = Storage()
    backend = _require_backend()
    pages = dedupe_pages(pages)
    url_to_doc_id = {page.url: page.doc_id for page in pages}
    graph = {page.doc_id: _pagerank_targets(page, url_to_doc_id) for page in pages}
    pagerank = compute_pagerank(graph, iterations=12, tolerance=1e-6)
    if reset:
        backend.recreate_index()
    elif not backend.client.indices.exists(index=backend.index_name):
        backend.recreate_index()
    suggestions: Counter[str] = Counter()

    def documents() -> Iterator[dict[str, object]]:
        for page in pages:
            save_snapshot(page, settings.snapshot_dir)
            for term, weight in extract_suggestion_terms(page.title, page.text):
                suggestions[term] += weight
            yield _index_document(page, pagerank)

    count = backend.index_document_stream(documents(), chunk_size=INDEX_CHUNK_SIZE, progress_every=0)
    flush_suggestions(storage, suggestions)
    return count


def index_path(path: Path, reset: bool = False) -> int:
    settings = get_settings()
    storage = Storage()
    backend = _require_backend()
    started = time.monotonic()
    print(f"Input: {path}", flush=True)
    url_to_doc_id, scanned = collect_url_map(path)
    if not url_to_doc_id:
        raise SystemExit(f"No crawled pages found in {path}")
    print(f"Scan complete: {scanned} lines, {len(url_to_doc_id)} unique URLs", flush=True)
    graph = build_graph(path, url_to_doc_id)
    print(f"Computing PageRank for {len(graph)} pages", flush=True)
    pagerank = compute_pagerank(graph, iterations=12, tolerance=1e-6)
    print("PageRank complete", flush=True)
    if reset:
        print(f"Recreating Elasticsearch index: {backend.index_name}", flush=True)
        backend.recreate_index()
    elif not backend.client.indices.exists(index=backend.index_name):
        print(f"Creating Elasticsearch index: {backend.index_name}", flush=True)
        backend.recreate_index()
    suggestions: Counter[str] = Counter()
    documents = stream_index_documents(path, pagerank, settings.snapshot_dir, suggestions)
    count = backend.index_document_stream(
        documents,
        chunk_size=INDEX_CHUNK_SIZE,
        progress_every=INDEX_PROGRESS_EVERY,
    )
    suggestion_count = flush_suggestions(storage, suggestions)
    elapsed = time.monotonic() - started
    print(f"Indexed {count} documents into Elasticsearch", flush=True)
    print(f"Updated {suggestion_count} suggestion terms", flush=True)
    print(f"Elapsed {elapsed:.1f}s", flush=True)
    return count


def resolve_input(input_path: Path | None) -> Path:
    settings = get_settings()
    if input_path:
        return input_path
    if settings.clean_crawl_output.exists():
        return settings.clean_crawl_output
    if settings.crawl_output.exists():
        return settings.crawl_output
    return SAMPLE_DOCUMENTS_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Elasticsearch index for NKU search.")
    parser.add_argument("--input", type=Path, default=None, help="JSONL crawler output. Defaults to crawl output or sample data.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the ES index.")
    return parser.parse_args()


def main() -> None:
    ensure_data_dirs()
    args = parse_args()
    path = resolve_input(args.input)
    index_path(path, reset=args.reset)


if __name__ == "__main__":
    main()


