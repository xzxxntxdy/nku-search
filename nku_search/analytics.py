from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlparse

from .config import SAMPLE_DOCUMENTS_PATH
from .index import load_pages
from .ranking import compute_pagerank
from .text import tokenize


def analyze_pages(input_path: Path) -> dict[str, object]:
    pages = load_pages(input_path)
    domains = Counter(urlparse(page.url).netloc for page in pages)
    filetypes = Counter(page.filetype for page in pages)
    top_terms: Counter[str] = Counter()
    graph = {page.doc_id: [] for page in pages}
    url_to_doc_id = {page.url: page.doc_id for page in pages}
    for page in pages:
        top_terms.update(token for token in tokenize(f"{page.title} {page.text}") if len(token) >= 2)
        graph[page.doc_id] = [url_to_doc_id[url] for url in page.outgoing_links if url in url_to_doc_id]
    ranks = compute_pagerank(graph)
    ranked_pages = sorted(pages, key=lambda page: ranks.get(page.doc_id, 0.0), reverse=True)[:10]
    text_lengths = [len(page.text) for page in pages]
    edge_count = sum(len(links) for links in graph.values())
    return {
        "input": str(input_path),
        "document_count": len(pages),
        "domain_count": len(domains),
        "domains": dict(domains.most_common(20)),
        "filetypes": dict(filetypes.most_common()),
        "edge_count": edge_count,
        "avg_text_length": round(sum(text_lengths) / max(len(text_lengths), 1), 2),
        "max_text_length": max(text_lengths) if text_lengths else 0,
        "top_terms": dict(top_terms.most_common(30)),
        "top_pagerank": [
            {
                "title": page.title,
                "url": page.url,
                "pagerank": round(ranks.get(page.doc_id, 0.0), 8),
            }
            for page in ranked_pages
        ],
    }


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# 运行分析报告",
        "",
        f"- 输入文件：`{report['input']}`",
        f"- 文档数量：{report['document_count']}",
        f"- 域名数量：{report['domain_count']}",
        f"- 链接边数量：{report['edge_count']}",
        f"- 平均正文长度：{report['avg_text_length']}",
        f"- 最大正文长度：{report['max_text_length']}",
        "",
        "## 域名分布",
        "",
    ]
    for domain, count in dict(report["domains"]).items():
        lines.append(f"- `{domain}`：{count}")
    lines.extend(["", "## 文件类型分布", ""])
    for filetype, count in dict(report["filetypes"]).items():
        lines.append(f"- `{filetype}`：{count}")
    lines.extend(["", "## 高频词", ""])
    for term, count in dict(report["top_terms"]).items():
        lines.append(f"- `{term}`：{count}")
    lines.extend(["", "## PageRank Top 页面", ""])
    for item in report["top_pagerank"]:
        lines.append(f"- {item['pagerank']} [{item['title']}]({item['url']})")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze crawled NKU documents.")
    parser.add_argument("--input", type=Path, default=SAMPLE_DOCUMENTS_PATH)
    parser.add_argument("--output", type=Path, default=None, help="Write markdown report to this path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = analyze_pages(args.input)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    markdown = render_markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
