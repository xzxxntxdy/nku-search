from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from .config import get_settings
from .local_index import LocalInvertedIndex
from .models import CrawledPage, SearchDiagnostics, SearchFacet, SearchHit
from .query import SearchQuery, build_es_query
from .text import make_snippet


INDEX_MAPPING: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "30s",
        "max_result_window": 200000,
        "analysis": {
            "analyzer": {
                "nku_cn": {
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "url": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "nku_cn", "fields": {"keyword": {"type": "keyword"}}},
            "text": {"type": "text", "analyzer": "nku_cn"},
            "anchors": {"type": "text", "analyzer": "nku_cn"},
            "outgoing_links": {"type": "keyword"},
            "content_type": {"type": "keyword"},
            "filetype": {"type": "keyword"},
            "section": {"type": "keyword"},
            "category": {"type": "keyword"},
            "fetched_at": {"type": "date"},
            "status": {"type": "integer"},
            "pagerank": {"type": "float"},
            "snapshot_path": {"type": "keyword"},
        }
    },
}


class SearchBackend:
    def __init__(self, elasticsearch_url: str | None = None, index_name: str | None = None) -> None:
        settings = get_settings()
        self.elasticsearch_url = elasticsearch_url or settings.elasticsearch_url
        self.index_name = index_name or settings.index_name
        self._client: Any | None = None
        self.last_diagnostics = SearchDiagnostics("Elasticsearch", 0.0, 0, 0, [])

    @property
    def client(self) -> Any:
        if self._client is None:
            from elasticsearch import Elasticsearch

            self._client = Elasticsearch(self.elasticsearch_url, request_timeout=120)
        return self._client

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def recreate_index(self) -> None:
        if self.client.indices.exists(index=self.index_name):
            self.client.indices.delete(index=self.index_name)
        self.client.indices.create(index=self.index_name, body=INDEX_MAPPING)

    def index_documents(self, documents: list[dict[str, Any]]) -> int:
        from elasticsearch.helpers import bulk

        actions = [
            {
                "_index": self.index_name,
                "_id": document["doc_id"],
                "_source": document,
            }
            for document in documents
        ]
        success, _ = bulk(self.client, actions, refresh=True)
        return int(success)

    def _result_window(self) -> int:
        try:
            settings = self.client.indices.get_settings(index=self.index_name)
            value = settings[self.index_name]["settings"]["index"].get("max_result_window", 10000)
            return int(value)
        except Exception:
            return 10000

    def _facets_from_response(self, response: dict[str, Any]) -> list[SearchFacet]:
        facets: list[SearchFacet] = []
        for name, payload in response.get("aggregations", {}).items():
            buckets = {
                str(bucket.get("key", "")): int(bucket.get("doc_count", 0))
                for bucket in payload.get("buckets", [])
                if str(bucket.get("key", ""))
            }
            facets.append(SearchFacet(name, buckets))
        return facets

    def index_document_stream(
        self,
        documents: Iterable[dict[str, Any]],
        chunk_size: int = 500,
        progress_every: int = 1000,
    ) -> int:
        from elasticsearch.helpers import streaming_bulk

        def actions() -> Iterable[dict[str, Any]]:
            for document in documents:
                yield {
                    "_index": self.index_name,
                    "_id": document["doc_id"],
                    "_source": document,
                }

        success = 0
        failed = 0
        for ok, item in streaming_bulk(
            self.client,
            actions(),
            chunk_size=chunk_size,
            request_timeout=120,
            raise_on_error=False,
            raise_on_exception=False,
        ):
            if ok:
                success += 1
            else:
                failed += 1
                if failed <= 5:
                    print(f"Elasticsearch rejected document: {item}", flush=True)
            total = success + failed
            if progress_every and total % progress_every == 0:
                print(f"Indexed {success} documents ({failed} failed)", flush=True)
        self.client.indices.refresh(index=self.index_name)
        if failed:
            raise RuntimeError(f"Elasticsearch bulk import failed for {failed} documents")
        return success

    def search(self, query: SearchQuery, user_terms: list[str] | None = None) -> tuple[list[SearchHit], int]:
        result_window = self._result_window()
        if query.offset >= result_window:
            count_query = replace(query, page=1, size=0)
            response = self.client.search(index=self.index_name, body=build_es_query(count_query, user_terms))
            total = response.get("hits", {}).get("total", {}).get("value", 0)
            self.last_diagnostics = SearchDiagnostics(
                backend="Elasticsearch",
                took_ms=float(response.get("took", 0)),
                total_candidates=int(total),
                total_matches=int(total),
                facets=self._facets_from_response(response),
            )
            return [], int(total)

        effective_query = query
        if query.offset + query.size > result_window:
            effective_query = replace(query, size=max(result_window - query.offset, 0))
        response = self.client.search(index=self.index_name, body=build_es_query(effective_query, user_terms))
        hits = response.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        self.last_diagnostics = SearchDiagnostics(
            backend="Elasticsearch",
            took_ms=float(response.get("took", 0)),
            total_candidates=int(total),
            total_matches=int(total),
            facets=self._facets_from_response(response),
        )
        results: list[SearchHit] = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            highlight = hit.get("highlight", {})
            snippet = (
                " ".join(highlight.get("text", []))
                or " ".join(highlight.get("title", []))
                or make_snippet(source.get("text", ""), query.q)
                or source.get("title", source.get("url", ""))
            )
            results.append(
                SearchHit(
                    doc_id=source.get("doc_id", hit.get("_id", "")),
                    url=source.get("url", ""),
                    title=source.get("title", source.get("url", "Untitled")),
                    snippet=snippet,
                    score=float(hit.get("_score", 0.0)),
                    pagerank=float(source.get("pagerank", 0.0)),
                    filetype=source.get("filetype", "html"),
                    fetched_at=source.get("fetched_at", ""),
                    section=source.get("section", "main"),
                    category=source.get("category", "瀛︽牎闂ㄦ埛"),
                    snapshot_path=source.get("snapshot_path", ""),
                    explanation={"es_score": float(hit.get("_score", 0.0))},
                )
            )
        return results, int(total)


class LocalSearchBackend:
    """Small in-process backend for tests, demos, and machines without Elasticsearch."""

    def __init__(self, pages: list[CrawledPage] | None = None) -> None:
        self.pages = pages or []
        self.index = LocalInvertedIndex(self.pages)

    @classmethod
    def from_jsonl(cls, path: Path) -> "LocalSearchBackend":
        pages: list[CrawledPage] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    pages.append(CrawledPage.from_dict(json.loads(line)))
        return cls(pages)

    def search(self, query: SearchQuery, user_terms: list[str] | None = None) -> tuple[list[SearchHit], int]:
        return self.index.search(query, user_terms)








