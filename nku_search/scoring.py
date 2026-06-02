from __future__ import annotations

from dataclasses import dataclass
from math import log


@dataclass(frozen=True, slots=True)
class TermStats:
    total_docs: int
    doc_freq: int
    term_freq: int
    field_length: int
    avg_field_length: float
    field_boost: float = 1.0


class WeightingModel:
    """Small scoring interface modeled after mature IR libraries."""

    name = "base"

    def score(self, stats: TermStats) -> float:
        raise NotImplementedError

    def idf(self, total_docs: int, doc_freq: int) -> float:
        return log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))


@dataclass(frozen=True, slots=True)
class BM25FModel(WeightingModel):
    k1: float = 1.5
    b: float = 0.75
    name: str = "bm25f"

    def score(self, stats: TermStats) -> float:
        if stats.doc_freq <= 0 or stats.term_freq <= 0:
            return 0.0
        avg_length = max(stats.avg_field_length, 1.0)
        length = max(stats.field_length, 1)
        tf = stats.term_freq
        denom = tf + self.k1 * (1 - self.b + self.b * length / avg_length)
        return stats.field_boost * self.idf(stats.total_docs, stats.doc_freq) * (tf * (self.k1 + 1)) / denom


@dataclass(frozen=True, slots=True)
class TfIdfModel(WeightingModel):
    name: str = "tfidf"

    def score(self, stats: TermStats) -> float:
        if stats.doc_freq <= 0 or stats.term_freq <= 0:
            return 0.0
        return stats.field_boost * stats.term_freq * self.idf(stats.total_docs, stats.doc_freq)

