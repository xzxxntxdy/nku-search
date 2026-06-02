from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FieldType(StrEnum):
    TEXT = "text"
    KEYWORD = "keyword"
    DATE = "date"
    FLOAT = "float"
    INTEGER = "integer"


@dataclass(frozen=True, slots=True)
class SearchField:
    name: str
    field_type: FieldType
    stored: bool = True
    indexed: bool = True
    scorable: bool = True
    boost: float = 1.0


@dataclass(frozen=True, slots=True)
class SearchSchema:
    fields: tuple[SearchField, ...]

    def __getitem__(self, name: str) -> SearchField:
        for field in self.fields:
            if field.name == name:
                return field
        raise KeyError(name)

    def names(self) -> list[str]:
        return [field.name for field in self.fields]

    def text_fields(self) -> list[SearchField]:
        return [field for field in self.fields if field.field_type == FieldType.TEXT and field.indexed]

    def scorable_text_fields(self) -> list[SearchField]:
        return [field for field in self.text_fields() if field.scorable]


DEFAULT_SCHEMA = SearchSchema(
    fields=(
        SearchField("title", FieldType.TEXT, boost=3.2),
        SearchField("anchors", FieldType.TEXT, boost=2.0),
        SearchField("text", FieldType.TEXT, boost=1.0),
        SearchField("url", FieldType.KEYWORD, scorable=False),
        SearchField("filetype", FieldType.KEYWORD, scorable=False),
        SearchField("section", FieldType.KEYWORD, scorable=False),
        SearchField("category", FieldType.KEYWORD, scorable=False),
        SearchField("fetched_at", FieldType.DATE, scorable=False),
        SearchField("pagerank", FieldType.FLOAT, scorable=False),
        SearchField("status", FieldType.INTEGER, scorable=False),
    )
)
