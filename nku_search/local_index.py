from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import time
from urllib.parse import urlparse

from .advanced_query import ParsedQuery, parse_advanced_query
from .models import CrawledPage, SearchDiagnostics, SearchFacet, SearchHit
from .query import QueryMode, SearchQuery, site_prefix_filters, wildcard_to_regex
from .ranking import compute_pagerank, infer_interest_score
from .schema import DEFAULT_SCHEMA, SearchSchema
from .scoring import BM25FModel, TermStats, WeightingModel
from .text import make_snippet, tokenize


@dataclass(slots=True)
class IndexedPage:
    page: CrawledPage
    field_terms: dict[str, Counter[str]]
    field_lengths: dict[str, int]
    combined_text: str
    combined_terms: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class RankingWeights:
    bm25: float = 1.0
    phrase: float = 1.0
    title: float = 1.0
    url: float = 0.35
    pagerank: float = 0.15
    freshness: float = 0.08
    personal: float = 0.20


@dataclass(frozen=True, slots=True)
class SearchFeatureVector:
    bm25: float
    phrase: float
    title: float
    url: float
    pagerank: float
    freshness: float
    personal: float

    def total(self, weights: RankingWeights) -> float:
        return (
            weights.bm25 * self.bm25
            + weights.phrase * self.phrase
            + weights.title * self.title
            + weights.url * self.url
            + weights.pagerank * self.pagerank
            + weights.freshness * self.freshness
            + weights.personal * self.personal
        )

    def explain(self) -> dict[str, float]:
        return {
            "bm25": round(self.bm25, 6),
            "phrase": round(self.phrase, 6),
            "title": round(self.title, 6),
            "url": round(self.url, 6),
            "pagerank": round(self.pagerank, 6),
            "freshness": round(self.freshness, 6),
            "personal": round(self.personal, 6),
        }


class LocalInvertedIndex:
    """A dependency-light BM25 inverted index used for demos, tests, and offline grading."""

    def __init__(
        self,
        pages: list[CrawledPage],
        schema: SearchSchema = DEFAULT_SCHEMA,
        weighting: WeightingModel | None = None,
        ranking_weights: RankingWeights | None = None,
    ) -> None:
        self.pages = pages
        self.schema = schema
        self.weighting = weighting or BM25FModel()
        self.ranking_weights = ranking_weights or RankingWeights()
        self.scorable_fields = self.schema.scorable_text_fields()
        self.documents: dict[str, IndexedPage] = {}
        self.postings: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
        self.doc_freq: Counter[str] = Counter()
        self.pagerank: dict[str, float] = {}
        self.avg_field_length = {field.name: 0.0 for field in self.scorable_fields}
        self.vocabulary: set[str] = set()
        self.last_diagnostics = SearchDiagnostics("LocalInvertedIndex", 0.0, 0, 0)
        self._build()

    def _build(self) -> None:
        totals = Counter()
        for page in self.pages:
            fields = {
                "title": page.title,
                "anchors": " ".join(page.anchors),
                "text": page.text,
            }
            field_terms = {field.name: Counter(tokenize(fields.get(field.name, ""))) for field in self.scorable_fields}
            field_lengths = {name: sum(counter.values()) for name, counter in field_terms.items()}
            combined_text = f"{page.title} {' '.join(page.anchors)} {page.text}"
            combined_terms = set().union(*(counter.keys() for counter in field_terms.values()))
            indexed = IndexedPage(page, field_terms, field_lengths, combined_text, combined_terms)
            self.documents[page.doc_id] = indexed
            for field_name, counter in field_terms.items():
                totals[field_name] += field_lengths[field_name]
                for term, count in counter.items():
                    self.postings[term].setdefault(page.doc_id, {})[field_name] = count
                    self.vocabulary.add(term)
            self.doc_freq.update(combined_terms)

        doc_count = max(len(self.documents), 1)
        self.avg_field_length = {
            field.name: max(totals[field.name] / doc_count, 1.0)
            for field in self.scorable_fields
        }
        url_to_doc_id = {indexed.page.url: doc_id for doc_id, indexed in self.documents.items()}
        graph = {
            doc_id: [url_to_doc_id[url] for url in indexed.page.outgoing_links if url in url_to_doc_id]
            for doc_id, indexed in self.documents.items()
        }
        self.pagerank = compute_pagerank(graph)

    @property
    def doc_count(self) -> int:
        return len(self.documents)

    def search(self, query: SearchQuery, user_terms: list[str] | None = None) -> tuple[list[SearchHit], int]:
        started = time.perf_counter()
        parsed = parse_advanced_query(
            query.q,
            str(query.mode),
            query.site,
            query.filetype,
            section=query.section,
            category=query.category,
        )
        candidates = self._initial_candidates(parsed)
        total_candidates = len(candidates)
        candidates = self._apply_filters(candidates, parsed)
        expanded_terms = self._expand_terms(parsed)
        scored: list[tuple[str, float, dict[str, float | str], list[str]]] = []
        for doc_id in candidates:
            indexed = self.documents[doc_id]
            if not self._matches(indexed, parsed, expanded_terms):
                continue
            features = self._features(doc_id, indexed, parsed, expanded_terms, user_terms or [])
            score = features.total(self.ranking_weights)
            if score <= 0 and (parsed.phrases or parsed.regex_patterns):
                score = 0.05 + features.personal
            matched_terms = [term for term in expanded_terms if term in indexed.combined_terms]
            explanation = features.explain()
            scored.append((doc_id, score, explanation, matched_terms))

        scored.sort(key=lambda item: item[1], reverse=True)
        hits = [self._to_hit(doc_id, score, explanation, matched_terms, query.q) for doc_id, score, explanation, matched_terms in scored[query.offset : query.offset + query.size]]
        self.last_diagnostics = SearchDiagnostics(
            backend="LocalInvertedIndex",
            took_ms=round((time.perf_counter() - started) * 1000, 3),
            total_candidates=total_candidates,
            total_matches=len(scored),
            facets=self.facets([doc_id for doc_id, *_ in scored]),
        )
        return hits, len(scored)

    def _initial_candidates(self, parsed: ParsedQuery) -> set[str]:
        if parsed.terms or parsed.title_terms:
            candidates: set[str] = set()
            for term in parsed.terms + parsed.title_terms:
                candidates.update(self.postings.get(term, {}))
            return candidates or set(self.documents)
        return set(self.documents)

    def _apply_filters(self, candidates: set[str], parsed: ParsedQuery) -> set[str]:
        filtered: set[str] = set()
        for doc_id in candidates:
            page = self.documents[doc_id].page
            if parsed.site:
                prefixes = [item["prefix"]["url"] for item in site_prefix_filters(parsed.site)]
                if prefixes and not any(page.url.startswith(prefix) for prefix in prefixes):
                    continue
                if not prefixes and not page.url.startswith(parsed.site):
                    continue
            if parsed.filetype and page.filetype.lower() != parsed.filetype.lower():
                continue
            if parsed.section and page.section != parsed.section:
                continue
            if parsed.category and page.category != parsed.category:
                continue
            if parsed.after and page.fetched_at and page.fetched_at[:10] < parsed.after:
                continue
            if parsed.before and page.fetched_at and page.fetched_at[:10] > parsed.before:
                continue
            if parsed.url_terms and not all(term in page.url.lower() for term in parsed.url_terms):
                continue
            filtered.add(doc_id)
        return filtered

    def _expand_terms(self, parsed: ParsedQuery) -> list[str]:
        terms = list(parsed.positive_terms)
        for pattern in parsed.wildcard_patterns:
            regex = wildcard_to_regex(pattern)
            terms.extend(term for term in self.vocabulary if regex.fullmatch(term) or regex.search(term))
        return list(dict.fromkeys(terms))

    def _matches(self, indexed: IndexedPage, parsed: ParsedQuery, expanded_terms: list[str]) -> bool:
        text = indexed.combined_text.lower()
        if parsed.excluded_terms and any(term in indexed.combined_terms for term in parsed.excluded_terms):
            return False
        if parsed.title_terms and not all(term in indexed.field_terms["title"] for term in parsed.title_terms):
            return False
        if parsed.phrases and not all(phrase.lower() in text for phrase in parsed.phrases):
            return False
        for pattern in parsed.regex_patterns:
            try:
                if not re.search(pattern, text, re.IGNORECASE):
                    return False
            except re.error:
                return False
        if parsed.mode == QueryMode.WILDCARD and parsed.wildcard_patterns:
            return any(term in indexed.combined_terms for term in expanded_terms)
        if not expanded_terms and not parsed.phrases and not parsed.regex_patterns:
            return True
        return any(term in indexed.combined_terms for term in expanded_terms) or bool(parsed.phrases or parsed.regex_patterns)

    def _features(
        self,
        doc_id: str,
        indexed: IndexedPage,
        parsed: ParsedQuery,
        terms: list[str],
        user_terms: list[str],
    ) -> SearchFeatureVector:
        return SearchFeatureVector(
            bm25=self._bm25(indexed, terms),
            phrase=self._phrase_score(indexed, parsed),
            title=self._title_bonus(indexed, parsed),
            url=self._url_bonus(indexed, parsed, terms),
            pagerank=self.pagerank.get(doc_id, 0.0),
            freshness=self._freshness_score(indexed.page.fetched_at),
            personal=infer_interest_score(user_terms, indexed.page.title, indexed.page.text),
        )

    def _bm25(self, indexed: IndexedPage, terms: list[str]) -> float:
        score = 0.0
        total_docs = max(self.doc_count, 1)
        for term in terms:
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            for field in self.scorable_fields:
                tf = indexed.field_terms[field.name].get(term, 0)
                if tf == 0:
                    continue
                score += self.weighting.score(
                    TermStats(
                        total_docs=total_docs,
                        doc_freq=df,
                        term_freq=tf,
                        field_length=max(indexed.field_lengths[field.name], 1),
                        avg_field_length=self.avg_field_length[field.name],
                        field_boost=field.boost,
                    )
                )
        return score

    def _phrase_score(self, indexed: IndexedPage, parsed: ParsedQuery) -> float:
        score = 0.0
        lower_title = indexed.page.title.lower()
        lower_text = indexed.combined_text.lower()
        for phrase in parsed.phrases:
            phrase = phrase.lower()
            if phrase in lower_title:
                score += 2.5
            elif phrase in lower_text:
                score += 1.2
        return score

    def _title_bonus(self, indexed: IndexedPage, parsed: ParsedQuery) -> float:
        title_terms = parsed.title_terms or parsed.terms
        if not title_terms:
            return 0.0
        matches = sum(1 for term in title_terms if term in indexed.field_terms["title"])
        return matches / max(len(title_terms), 1)

    def _url_bonus(self, indexed: IndexedPage, parsed: ParsedQuery, terms: list[str]) -> float:
        url = indexed.page.url.lower()
        title_slug_hits = sum(1 for term in terms if term and term.lower() in url)
        url_filter_hits = sum(1 for term in parsed.url_terms if term in url)
        return min((title_slug_hits + url_filter_hits) / max(len(terms) or 1, 1), 1.0)

    def _freshness_score(self, fetched_at: str) -> float:
        if not fetched_at:
            return 0.0
        try:
            fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - fetched).days, 0)
        if age_days <= 30:
            return 1.0
        if age_days <= 365:
            return 0.5
        return 0.15

    def _to_hit(
        self,
        doc_id: str,
        score: float,
        explanation: dict[str, float | str],
        matched_terms: list[str],
        query: str,
    ) -> SearchHit:
        page = self.documents[doc_id].page
        return SearchHit(
            doc_id=page.doc_id,
            url=page.url,
            title=page.title or page.url,
            snippet=make_snippet(page.text, query),
            score=score,
            pagerank=self.pagerank.get(doc_id, 0.0),
            filetype=page.filetype,
            fetched_at=page.fetched_at,
            section=page.section,
            category=page.category,
            snapshot_path=f"{page.doc_id}.html",
            matched_terms=matched_terms[:12],
            explanation=explanation,
        )

    def facets(self, doc_ids: list[str] | None = None) -> list[SearchFacet]:
        ids = doc_ids or list(self.documents)
        filetypes: Counter[str] = Counter()
        domains: Counter[str] = Counter()
        sections: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for doc_id in ids:
            page = self.documents[doc_id].page
            filetypes[page.filetype] += 1
            domains[urlparse(page.url).netloc] += 1
            sections[page.section] += 1
            categories[page.category] += 1
        return [
            SearchFacet("filetype", dict(filetypes.most_common(8))),
            SearchFacet("domain", dict(domains.most_common(8))),
            SearchFacet("category", dict(categories.most_common(12))),
            SearchFacet("section", dict(sections.most_common(12))),
        ]
