from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .text import build_idf, cosine_similarity, tokenize


def compute_pagerank(
    graph: dict[str, list[str]],
    damping: float = 0.85,
    iterations: int = 30,
    tolerance: float = 1e-8,
) -> dict[str, float]:
    nodes = set(graph)
    for targets in graph.values():
        nodes.update(targets)
    if not nodes:
        return {}
    ranks = {node: 1.0 / len(nodes) for node in nodes}
    outgoing = {node: [target for target in graph.get(node, []) if target in nodes] for node in nodes}
    for _ in range(iterations):
        new_ranks = {node: (1.0 - damping) / len(nodes) for node in nodes}
        dangling = sum(ranks[node] for node, links in outgoing.items() if not links)
        dangling_share = damping * dangling / len(nodes)
        for node in nodes:
            new_ranks[node] += dangling_share
        for source, links in outgoing.items():
            if not links:
                continue
            share = damping * ranks[source] / len(links)
            for target in links:
                new_ranks[target] += share
        delta = sum(abs(new_ranks[node] - ranks[node]) for node in nodes)
        ranks = new_ranks
        if delta < tolerance:
            break
    return ranks


@dataclass(slots=True)
class LocalRankDocument:
    doc_id: str
    title: str
    text: str
    anchors: list[str]
    pagerank: float = 0.0
    user_boost: float = 0.0

    @property
    def combined_text(self) -> str:
        return f"{self.title} {' '.join(self.anchors)} {self.text}"


def score_document(
    query: str,
    document: LocalRankDocument,
    idf: dict[str, float] | None = None,
    pagerank_weight: float = 0.15,
    personalization_weight: float = 0.20,
) -> float:
    title_score = cosine_similarity(query, document.title, idf) * 1.8
    anchor_score = cosine_similarity(query, " ".join(document.anchors), idf) * 1.4
    body_score = cosine_similarity(query, document.text, idf)
    lexical = max(title_score, 0.0) + max(anchor_score, 0.0) + max(body_score, 0.0)
    link_score = pagerank_weight * document.pagerank
    personal = personalization_weight * document.user_boost
    return lexical + link_score + personal


def rank_documents(query: str, documents: list[LocalRankDocument]) -> list[tuple[LocalRankDocument, float]]:
    idf = build_idf(doc.combined_text for doc in documents)
    scored = [(doc, score_document(query, doc, idf)) for doc in documents]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def infer_interest_score(query_history: list[str], title: str, text: str) -> float:
    if not query_history:
        return 0.0
    interests = defaultdict(float)
    for query in query_history:
        for token in tokenize(query):
            interests[token] += 1.0
    haystack = set(tokenize(f"{title} {text}"))
    if not haystack:
        return 0.0
    matches = sum(weight for term, weight in interests.items() if term in haystack)
    return min(matches / max(sum(interests.values()), 1.0), 1.0)

