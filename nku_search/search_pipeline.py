from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .index import load_pages
from .local_index import LocalInvertedIndex
from .models import CrawledPage, SearchHit
from .query import SearchQuery, detect_mode
from .recommend import extract_suggestion_terms


@dataclass(slots=True)
class PipelineContext:
    query: SearchQuery
    pages: list[CrawledPage]
    user_terms: list[str] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)
    total: int = 0
    facets: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class PipelineComponent(Protocol):
    name: str

    def run(self, context: PipelineContext) -> PipelineContext:
        ...


class QueryNormalizer:
    name = "query_normalizer"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.query.q = " ".join((context.query.q or "").split())
        context.query.mode = detect_mode(context.query.q, str(context.query.mode))
        context.metadata[self.name] = {"query": context.query.q, "mode": str(context.query.mode)}
        return context


class InMemoryRetriever:
    name = "bm25f_retriever"

    def __init__(self) -> None:
        self._cache_key: tuple[str, ...] | None = None
        self._index: LocalInvertedIndex | None = None

    def run(self, context: PipelineContext) -> PipelineContext:
        key = tuple(page.doc_id for page in context.pages)
        if self._index is None or self._cache_key != key:
            self._index = LocalInvertedIndex(context.pages)
            self._cache_key = key
        context.hits, context.total = self._index.search(context.query, context.user_terms)
        context.facets = [
            {"name": facet.name, "buckets": facet.buckets}
            for facet in self._index.last_diagnostics.facets
        ]
        context.metadata[self.name] = {
            "total": context.total,
            "candidate_count": self._index.last_diagnostics.total_candidates,
            "took_ms": self._index.last_diagnostics.took_ms,
        }
        return context


class SuggestionBuilder:
    name = "suggestion_builder"

    def run(self, context: PipelineContext) -> PipelineContext:
        terms: list[str] = []
        for hit in context.hits[:5]:
            terms.extend(term for term, _ in extract_suggestion_terms(hit.title, hit.snippet, limit=4))
        context.suggestions = list(dict.fromkeys(terms))[:12]
        context.metadata[self.name] = {"count": len(context.suggestions)}
        return context


class SearchPipeline:
    """Haystack-style component pipeline for local search execution."""

    def __init__(self, components: list[PipelineComponent] | None = None) -> None:
        self.components = components or [QueryNormalizer(), InMemoryRetriever(), SuggestionBuilder()]

    def run(
        self,
        query: SearchQuery,
        pages: list[CrawledPage],
        user_terms: list[str] | None = None,
    ) -> PipelineContext:
        context = PipelineContext(query=query, pages=pages, user_terms=user_terms or [])
        for component in self.components:
            context = component.run(context)
        return context

    def describe(self) -> dict[str, Any]:
        return {
            "style": "Haystack-like component pipeline",
            "components": [component.name for component in self.components],
            "inputs": ["SearchQuery", "CrawledPage[]", "user_terms[]"],
            "outputs": ["hits", "facets", "suggestions", "metadata"],
        }


def run_sample_pipeline(sample_path) -> PipelineContext:
    pages = load_pages(sample_path)
    return SearchPipeline().run(SearchQuery(q="信息检索"), pages)

