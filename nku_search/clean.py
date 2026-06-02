from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .frontier import canonicalize_frontier_url
from .text import clean_document_text, normalize_document_title


SERVICE_MARKERS = (
    "_visitcount",
    "_visitcountdisplay",
    "/_wp3services/",
    "/api/tracking",
    "/wp-admin",
)
SERVICE_PATH_SEGMENTS = {"login", "logout", "admin", "search"}
SUCCESS_STATUSES = {200, 202}


@dataclass(slots=True)
class CleanReport:
    input_path: str
    output_path: str
    input_lines: int = 0
    output_lines: int = 0
    unique_urls: int = 0
    dropped: Counter[str] = field(default_factory=Counter)
    sections: Counter[str] = field(default_factory=Counter)
    filetypes: Counter[str] = field(default_factory=Counter)
    statuses: Counter[str] = field(default_factory=Counter)
    domains: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "input_lines": self.input_lines,
            "output_lines": self.output_lines,
            "unique_urls": self.unique_urls,
            "dropped": dict(self.dropped),
            "sections": dict(self.sections.most_common()),
            "filetypes": dict(self.filetypes.most_common()),
            "statuses": dict(self.statuses.most_common()),
            "domains": dict(self.domains.most_common(30)),
        }


def is_service_url(url: str) -> bool:
    lowered = (url or "").lower()
    if any(marker in lowered for marker in SERVICE_MARKERS):
        return True
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    path = parsed.path.lower()
    segments = {segment for segment in path.split("/") if segment}
    if segments & SERVICE_PATH_SEGMENTS:
        return True
    if any(word in path for word in ("login", "logout", "/admin/")):
        return True
    filename = path.rsplit("/", 1)[-1]
    return filename.startswith("search") or filename in {"search", "login", "logout"}


def rejection_reason(item: dict[str, Any]) -> str | None:
    url = str(item.get("url") or "")
    if not url:
        return "empty_url"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid_url"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url"
    if is_service_url(url):
        return "service_url"
    try:
        status = int(item.get("status", 200))
    except Exception:
        return "invalid_status"
    if status not in SUCCESS_STATUSES:
        return "non_success_status"
    filetype = str(item.get("filetype") or "html").lower()
    title = str(item.get("title") or "")
    text = str(item.get("text") or "")
    html = str(item.get("html") or "")
    if filetype == "html" and not title.strip() and not text.strip() and not html.strip():
        return "empty_html_shell"
    return None


def quality_score(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
    text = str(item.get("text") or "")
    html = str(item.get("html") or "")
    title = str(item.get("title") or "")
    outgoing = item.get("outgoing_links") or []
    try:
        status = int(item.get("status", 0))
    except Exception:
        status = 0
    return (
        1 if status == 200 else 0,
        min(len(text), 2_000_000),
        min(len(html), 2_000_000),
        len(title),
        len(outgoing) if isinstance(outgoing, list) else 0,
    )


def canonical_key(url: str) -> str:
    return canonicalize_frontier_url(url) or url.strip()


def filtered_outgoing_links(links: Any) -> list[str]:
    if not isinstance(links, list):
        return []
    kept: dict[str, str] = {}
    for link in links:
        url = str(link or "")
        if not url or is_service_url(url):
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        kept.setdefault(canonical_key(url), url)
    return list(kept.values())


def normalize_clean_item(item: dict[str, Any]) -> dict[str, Any]:
    filetype = str(item.get("filetype") or "html").lower()
    if filetype != "html":
        item = dict(item)
        item["text"] = clean_document_text(str(item.get("text") or ""), filetype)
        item["title"] = normalize_document_title(
            str(item.get("url") or ""),
            filetype,
            text=str(item.get("text") or ""),
            fallback_title=str(item.get("title") or ""),
        )
    return item


def clean_jsonl(input_path: Path, output_path: Path, report_path: Path | None = None) -> CleanReport:
    report = CleanReport(str(input_path), str(output_path))
    best_by_url: dict[str, tuple[tuple[int, int, int, int, int], int]] = {}

    with input_path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            if not line.strip():
                report.dropped["blank_line"] += 1
                continue
            report.input_lines += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                report.dropped["bad_json"] += 1
                continue
            if not isinstance(item, dict):
                report.dropped["not_object"] += 1
                continue
            item = normalize_clean_item(item)
            reason = rejection_reason(item)
            if reason:
                report.dropped[reason] += 1
                continue
            key = canonical_key(str(item.get("url") or ""))
            score = quality_score(item)
            previous = best_by_url.get(key)
            if previous is None or score > previous[0]:
                best_by_url[key] = (score, line_no)

    selected_lines = {line_no for _score, line_no in best_by_url.values()}
    report.unique_urls = len(selected_lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line_no, line in enumerate(source, 1):
            if line_no not in selected_lines:
                continue
            item = normalize_clean_item(json.loads(line))
            item["outgoing_links"] = filtered_outgoing_links(item.get("outgoing_links"))
            target.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            report.output_lines += 1
            section = str(item.get("section") or "unknown")
            filetype = str(item.get("filetype") or "unknown").lower()
            status = str(item.get("status") or "unknown")
            domain = urlparse(str(item.get("url") or "")).netloc.lower()
            report.sections[section] += 1
            report.filetypes[filetype] += 1
            report.statuses[status] += 1
            report.domains[domain] += 1

    duplicate_drop_count = report.input_lines - report.output_lines - sum(report.dropped.values())
    if duplicate_drop_count > 0:
        report.dropped["duplicate_url"] = duplicate_drop_count

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(report), encoding="utf-8")
    return report


def render_report(report: CleanReport) -> str:
    data = report.to_dict()
    lines = [
        "# Crawl Data Cleaning Report",
        "",
        f"- Input: `{data['input_path']}`",
        f"- Output: `{data['output_path']}`",
        f"- Input records: {data['input_lines']}",
        f"- Output records: {data['output_lines']}",
        f"- Removed records: {data['input_lines'] - data['output_lines']}",
        "",
        "## Removed Records",
        "",
    ]
    for key, count in data["dropped"].items():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Section Distribution", ""])
    for key, count in data["sections"].items():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Filetype Distribution", ""])
    for key, count in data["filetypes"].items():
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Top Domains", ""])
    for key, count in data["domains"].items():
        lines.append(f"- `{key}`: {count}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean crawled NKU JSONL data before indexing.")
    parser.add_argument("--input", type=Path, default=Path("data/crawl/pages_160k.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/crawl/pages_160k_clean.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("docs/数据清洗报告.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = clean_jsonl(args.input, args.output, args.report)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


