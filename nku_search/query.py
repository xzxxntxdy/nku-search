from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any


class QueryMode(StrEnum):
    NORMAL = "normal"
    PHRASE = "phrase"
    WILDCARD = "wildcard"
    REGEX = "regex"


ADVANCED_OPERATOR_RE = re.compile(
    r'(?P<neg>-)?(?P<key>site|filetype|section|category|title|inurl|after|before):\s*(?P<value>"[^"]+"|\S+)'
)
PHRASE_QUOTES = {
    '"': '"',
    "“": "”",
    "‘": "’",
    "「": "」",
    "『": "』",
}


@dataclass(slots=True)
class SearchQuery:
    q: str
    mode: QueryMode = QueryMode.NORMAL
    site: str | None = None
    filetype: str | None = None
    section: str | None = None
    category: str | None = None
    page: int = 1
    size: int = 10

    @property
    def offset(self) -> int:
        return max(self.page - 1, 0) * self.size


SECTION_ALIASES = {
    "南开动漫": "anime",
    "动漫资源": "anime",
    "动漫": "anime",
}

CATEGORY_ALIASES = {
    "南开动漫": "动漫资源",
    "动漫": "动漫资源",
    "anime": "动漫资源",
}


def normalize_section(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return SECTION_ALIASES.get(value, value)


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return CATEGORY_ALIASES.get(value, value)


def detect_mode(query: str, explicit: str | None = None) -> QueryMode:
    if explicit:
        try:
            return QueryMode(explicit)
        except ValueError:
            pass
    stripped = query.strip()
    mode_target = ADVANCED_OPERATOR_RE.sub(" ", stripped).strip()
    if stripped.startswith("/") and stripped.endswith("/") and len(stripped) > 2:
        return QueryMode.REGEX
    if "*" in mode_target or "?" in mode_target:
        return QueryMode.WILDCARD
    if _strip_phrase_quotes(stripped) is not None:
        return QueryMode.PHRASE
    return QueryMode.NORMAL


def _strip_phrase_quotes(query: str) -> str | None:
    query = (query or "").strip()
    if len(query) < 2:
        return None
    right = PHRASE_QUOTES.get(query[0])
    if right and query.endswith(right):
        return query[1:-1].strip()
    return None


def clean_query(query: str, mode: QueryMode | None = None) -> str:
    query = (query or "").strip()
    mode = mode or detect_mode(query)
    if mode == QueryMode.PHRASE:
        phrase = _strip_phrase_quotes(query)
        if phrase is not None:
            return phrase
    if mode == QueryMode.REGEX and len(query) >= 2 and query[0] == query[-1] == "/":
        return query[1:-1].strip()
    return query


def wildcard_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(clean_query(pattern, QueryMode.WILDCARD))
    regex = escaped.replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(regex, re.IGNORECASE)


def site_prefix_filters(site: str | None) -> list[dict[str, Any]]:
    if not site:
        return []
    value = site.strip().strip('"').strip("'")
    if not value:
        return []
    has_scheme = bool(re.match(r"(?i)^https?://", value))
    if has_scheme:
        prefix = value
        if re.match(r"(?i)^https?://[^/]+$", prefix):
            prefix = f"{prefix}/"
        return [{"prefix": {"url": prefix}}]

    prefix = value.lstrip("/")
    if "/" not in prefix:
        prefix = f"{prefix.rstrip('/')}/"
    return [
        {"prefix": {"url": f"https://{prefix}"}},
        {"prefix": {"url": f"http://{prefix}"}},
    ]


def build_es_query(search: SearchQuery, user_terms: list[str] | None = None) -> dict[str, Any]:
    from .advanced_query import parse_advanced_query

    parsed = parse_advanced_query(
        search.q,
        str(search.mode),
        search.site,
        search.filetype,
        section=search.section,
        category=search.category,
    )
    has_advanced_filter = bool(
        parsed.site
        or parsed.filetype
        or parsed.section
        or parsed.category
        or parsed.after
        or parsed.before
        or parsed.url_terms
        or parsed.title_terms
        or parsed.excluded_terms
    )
    q = " ".join(parsed.terms)
    if not q and not has_advanced_filter:
        q = clean_query(search.q, search.mode)
    filters: list[dict[str, Any]] = []
    must_not: list[dict[str, Any]] = []
    should: list[dict[str, Any]] = []

    if parsed.site:
        site_filters = site_prefix_filters(parsed.site)
        if len(site_filters) == 1:
            filters.append(site_filters[0])
        elif site_filters:
            filters.append({"bool": {"should": site_filters, "minimum_should_match": 1}})
    if parsed.filetype:
        filters.append({"term": {"filetype": parsed.filetype.lower()}})
    parsed.section = normalize_section(parsed.section)
    parsed.category = normalize_category(parsed.category)
    if parsed.section:
        filters.append({"term": {"section": parsed.section}})
    if parsed.category:
        filters.append({"term": {"category": parsed.category}})
    if parsed.after or parsed.before:
        date_range: dict[str, str] = {}
        if parsed.after:
            date_range["gte"] = parsed.after
        if parsed.before:
            date_range["lte"] = parsed.before
        filters.append({"range": {"fetched_at": date_range}})
    for url_term in parsed.url_terms:
        filters.append({"wildcard": {"url": f"*{url_term}*"}})
    for excluded in parsed.excluded_terms:
        must_not.append(
            {
                "multi_match": {
                    "query": excluded,
                    "fields": ["title^3", "anchors^2", "text", "url"],
                }
            }
        )

    def phrase_match(phrase: str) -> dict[str, Any]:
        return {
            "multi_match": {
                "query": phrase,
                "type": "phrase",
                "fields": ["title^3", "anchors^2", "text"],
            }
        }

    if search.mode == QueryMode.PHRASE:
        phrase = parsed.phrases[0] if parsed.phrases else q
        must: list[dict[str, Any]] = [phrase_match(phrase)]
    elif search.mode == QueryMode.WILDCARD:
        wildcard = (parsed.wildcard_patterns[0] if parsed.wildcard_patterns else q).lower()
        must = [
            {
                "bool": {
                    "should": [
                        {"wildcard": {"title.keyword": {"value": f"*{wildcard}*", "boost": 3}}},
                        {"wildcard": {"text": {"value": f"*{wildcard}*"}}},
                        {"wildcard": {"anchors": {"value": f"*{wildcard}*", "boost": 2}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        ]
    elif search.mode == QueryMode.REGEX:
        pattern = parsed.regex_patterns[0] if parsed.regex_patterns else q
        must = [
            {
                "bool": {
                    "should": [
                        {"regexp": {"title.keyword": {"value": pattern, "boost": 3}}},
                        {"regexp": {"text": {"value": pattern}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        ]
    else:
        if q:
            must = [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["title^3", "anchors^2", "text", "url"],
                        "type": "best_fields",
                    }
                }
            ]
        else:
            must = [{"match_all": {}}]

    if search.mode != QueryMode.PHRASE and parsed.phrases:
        must.extend(phrase_match(phrase) for phrase in parsed.phrases)

    for title_term in parsed.title_terms:
        must.append({"match": {"title": {"query": title_term, "boost": 2.5}}})

    for term in user_terms or []:
        if term:
            should.append({"match": {"text": {"query": term, "boost": 0.4}}})

    return {
        "track_total_hits": True,
        "_source": {"excludes": ["text", "anchors", "outgoing_links"]},
        "from": search.offset,
        "size": search.size,
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": must,
                        "filter": filters,
                        "must_not": must_not,
                        "should": should,
                    }
                },
                "field_value_factor": {
                    "field": "pagerank",
                    "factor": 0.15,
                    "modifier": "ln1p",
                    "missing": 0,
                },
                "boost_mode": "sum",
                "score_mode": "sum",
            }
        },
        "highlight": {
            "max_analyzed_offset": 100000,
            "fields": {
                "title": {},
                "text": {"fragment_size": 160, "number_of_fragments": 1},
            }
        },
        "aggs": {
            "filetype": {"terms": {"field": "filetype", "size": 20}},
            "category": {"terms": {"field": "category", "size": 12}},
            "section": {"terms": {"field": "section", "size": 12}},
        },
    }








