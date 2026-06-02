from __future__ import annotations

from collections import Counter

from .storage import Storage
from .text import tokenize


def extract_suggestion_terms(title: str, text: str, limit: int = 8) -> list[tuple[str, float]]:
    counts = Counter(tokenize(f"{title} {text[:2000]}"))
    ignored = {"http", "https", "www", "edu", "cn", "html", "htm"}
    items = [
        (term, float(count))
        for term, count in counts.items()
        if len(term) >= 2 and term not in ignored and not term.isdigit()
    ]
    items.sort(key=lambda item: item[1], reverse=True)
    return items[:limit]


def update_suggestions_from_document(storage: Storage, title: str, text: str) -> None:
    for term, weight in extract_suggestion_terms(title, text):
        storage.upsert_suggestion(term, weight, "index")


def update_suggestions_from_query(storage: Storage, query: str, user_id: int | None = None) -> None:
    query = query.strip()
    if not query:
        return
    if user_id is not None:
        return
    storage.upsert_suggestion(query, 2.0, "query")
    for token in tokenize(query):
        if len(token) >= 2:
            storage.upsert_suggestion(token, 1.0, "query_term")
