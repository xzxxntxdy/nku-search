from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CrawledPage:
    url: str
    title: str
    text: str
    html: str = ""
    anchors: list[str] = field(default_factory=list)
    outgoing_links: list[str] = field(default_factory=list)
    content_type: str = "text/html"
    filetype: str = "html"
    section: str = "main"
    category: str = "学校门户"
    fetched_at: str = field(default_factory=utc_now_iso)
    status: int = 200

    @property
    def doc_id(self) -> str:
        import hashlib

        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()

    def to_index_document(self, pagerank: float = 0.0) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "anchors": self.anchors,
            "outgoing_links": self.outgoing_links,
            "content_type": self.content_type,
            "filetype": self.filetype,
            "section": self.section,
            "category": self.category,
            "fetched_at": self.fetched_at,
            "status": self.status,
            "pagerank": pagerank,
            "snapshot_path": f"{self.doc_id}.html",
        }

    def to_json_line(self) -> str:
        import json

        return json.dumps(
            {
                "url": self.url,
                "title": self.title,
                "text": self.text,
                "html": self.html,
                "anchors": self.anchors,
                "outgoing_links": self.outgoing_links,
                "content_type": self.content_type,
                "filetype": self.filetype,
                "section": self.section,
                "category": self.category,
                "fetched_at": self.fetched_at,
                "status": self.status,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawledPage":
        return cls(
            url=str(data.get("url", "")),
            title=str(data.get("title", "")),
            text=str(data.get("text", "")),
            html=str(data.get("html", "")),
            anchors=list(data.get("anchors", [])),
            outgoing_links=list(data.get("outgoing_links", [])),
            content_type=str(data.get("content_type", "text/html")),
            filetype=str(data.get("filetype", "html")),
            section=str(data.get("section", "main")),
            category=str(data.get("category", "学校门户")),
            fetched_at=str(data.get("fetched_at", utc_now_iso())),
            status=int(data.get("status", 200)),
        )


@dataclass(slots=True)
class SearchHit:
    doc_id: str
    url: str
    title: str
    snippet: str
    score: float
    pagerank: float
    filetype: str
    fetched_at: str
    section: str = "main"
    category: str = "学校门户"
    snapshot_path: str = ""
    matched_terms: list[str] = field(default_factory=list)
    explanation: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class SearchFacet:
    name: str
    buckets: dict[str, int]


@dataclass(slots=True)
class SearchDiagnostics:
    backend: str
    took_ms: float
    total_candidates: int
    total_matches: int
    facets: list[SearchFacet] = field(default_factory=list)
