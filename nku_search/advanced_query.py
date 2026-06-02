from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re

from .query import QueryMode, clean_query, detect_mode
from .text import tokenize


OPERATOR_RE = re.compile(
    r'(?P<neg>-)?(?P<key>site|filetype|section|category|title|inurl|after|before):\s*'
    r'(?P<value>"[^"]+"|“[^”]+”|‘[^’]+’|「[^」]+」|『[^』]+』|\S+)'
)
PHRASE_RE = re.compile(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’|「([^」]+)」|『([^』]+)』')
QUOTE_PAIRS = {
    '"': '"',
    "“": "”",
    "‘": "’",
    "「": "」",
    "『": "』",
}


@dataclass(slots=True)
class ParsedQuery:
    raw: str
    mode: QueryMode
    terms: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    wildcard_patterns: list[str] = field(default_factory=list)
    regex_patterns: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    title_terms: list[str] = field(default_factory=list)
    url_terms: list[str] = field(default_factory=list)
    site: str | None = None
    filetype: str | None = None
    section: str | None = None
    category: str | None = None
    after: str | None = None
    before: str | None = None

    @property
    def positive_terms(self) -> list[str]:
        items: list[str] = []
        items.extend(self.terms)
        for phrase in self.phrases:
            items.extend(tokenize(phrase))
        items.extend(self.title_terms)
        return list(dict.fromkeys(items))


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and QUOTE_PAIRS.get(value[0]) == value[-1]:
        return value[1:-1]
    return value


def _valid_date(value: str) -> str | None:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def parse_advanced_query(
    raw: str,
    explicit_mode: str | None = None,
    site: str | None = None,
    filetype: str | None = None,
    section: str | None = None,
    category: str | None = None,
) -> ParsedQuery:
    raw = raw or ""
    mode = detect_mode(raw, explicit_mode)
    parsed = ParsedQuery(
        raw=raw,
        mode=mode,
        site=site or None,
        filetype=(filetype or None),
        section=section or None,
        category=category or None,
    )
    working = raw

    for match in OPERATOR_RE.finditer(raw):
        key = match.group("key")
        value = _strip_quotes(match.group("value"))
        neg = bool(match.group("neg"))
        if key == "site" and not neg:
            parsed.site = value
        elif key == "filetype" and not neg:
            parsed.filetype = value.lower().lstrip(".")
        elif key == "section" and not neg:
            parsed.section = value
        elif key == "category" and not neg:
            parsed.category = value
        elif key == "title":
            terms = tokenize(value)
            if neg:
                parsed.excluded_terms.extend(terms)
            else:
                parsed.title_terms.extend(terms)
        elif key == "inurl":
            if neg:
                parsed.excluded_terms.extend(tokenize(value))
            else:
                parsed.url_terms.append(value.lower())
        elif key == "after" and not neg:
            parsed.after = _valid_date(value)
        elif key == "before" and not neg:
            parsed.before = _valid_date(value)
        working = working.replace(match.group(0), " ")

    for match in PHRASE_RE.finditer(working):
        phrase = next((group for group in match.groups() if group is not None), "")
        phrase = phrase.strip()
        if phrase:
            parsed.phrases.append(phrase)
        working = working.replace(match.group(0), " ")

    if mode == QueryMode.PHRASE and not parsed.phrases:
        phrase = clean_query(raw, mode)
        if phrase:
            parsed.phrases.append(phrase)
            working = ""
    elif mode == QueryMode.REGEX:
        pattern = clean_query(raw, mode)
        if pattern:
            parsed.regex_patterns.append(pattern)
            working = ""
    elif mode == QueryMode.WILDCARD:
        pattern = clean_query(raw, mode)
        if pattern:
            parsed.wildcard_patterns.append(pattern)
            working = ""

    for token in working.split():
        token = token.strip()
        if not token:
            continue
        target = parsed.excluded_terms if token.startswith("-") else parsed.terms
        token = token[1:] if token.startswith("-") else token
        if "*" in token or "?" in token:
            parsed.wildcard_patterns.append(token)
        else:
            target.extend(tokenize(token))

    parsed.terms = list(dict.fromkeys(parsed.terms))
    parsed.phrases = list(dict.fromkeys(parsed.phrases))
    parsed.wildcard_patterns = list(dict.fromkeys(parsed.wildcard_patterns))
    parsed.regex_patterns = list(dict.fromkeys(parsed.regex_patterns))
    parsed.excluded_terms = list(dict.fromkeys(parsed.excluded_terms))
    parsed.title_terms = list(dict.fromkeys(parsed.title_terms))
    parsed.url_terms = list(dict.fromkeys(parsed.url_terms))
    return parsed
