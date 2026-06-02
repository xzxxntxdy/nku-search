from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import DOCUMENT_EXTENSIONS


MIN_HOMEWORK_PAGES = 100_000


@dataclass(frozen=True, slots=True)
class CrawlSection:
    key: str
    label: str
    category: str
    description: str
    seed_urls: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    match_domains: tuple[str, ...]
    include_patterns: tuple[str, ...]
    deny_patterns: tuple[str, ...]
    max_pages: int
    priority: int
    depth_limit: int
    politeness_delay: float
    concurrency_per_domain: int
    document_first: bool = False

    def to_public_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["seed_count"] = len(self.seed_urls)
        data["scale_hint"] = "可单独运行，也可与其他板块合并写入同一 JSONL 后统一建索引"
        return data


COMMON_DENY_PATTERNS = (
    r".*/login.*",
    r".*/logout.*",
    r".*/admin.*",
    r".*/wp-admin.*",
    r".*/search\?.*",
    r".*/\?.*page=.*",
    r".*_visitcount(?:[?#].*)?$",
    r".*/_wp3services/.*",
    r".*/api/tracking.*",
    r"https?://(opac|ic)\.lib\.nankai\.edu\.cn/.*",
    r"https?://tech\.math\.nankai\.edu\.cn/.*",
    r"https?://jc\.nankai\.edu\.cn/.*",
    r"https?://jcen\.nankai\.edu\.cn/.*",
    r"(?i).*\.(?:zip|rar|7z|tar|gz|bz2|xz|iso|dmg|exe|msi|mp4|mp3|avi|mov|wmv)(?:[?#].*)?$",
)


CRAWL_SECTIONS: tuple[CrawlSection, ...] = (
    CrawlSection(
        key="news",
        label="新闻公告",
        category="新闻资讯",
        description="南开新闻网、通知公告、媒体南开、院系动态和专题新闻。",
        seed_urls=(
            "https://news.nankai.edu.cn/",
            "https://news.nankai.edu.cn/ywsd/index.shtml",
            "https://news.nankai.edu.cn/zhxw/index.shtml",
            "https://news.nankai.edu.cn/mtnk/index.shtml",
        ),
        allowed_domains=("news.nankai.edu.cn",),
        match_domains=("news.nankai.edu.cn",),
        include_patterns=(r"https?://news\.nankai\.edu\.cn/.*",),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=36_000,
        priority=100,
        depth_limit=8,
        politeness_delay=0.7,
        concurrency_per_domain=2,
    ),
    CrawlSection(
        key="main",
        label="学校主站",
        category="学校门户",
        description="学校概况、机构设置、人才培养、招生就业、校园服务等主站信息。",
        seed_urls=(
            "https://www.nankai.edu.cn/",
            "https://www.nankai.edu.cn/162/list.htm",
            "https://www.nankai.edu.cn/212/list.htm",
            "https://www.nankai.edu.cn/223/list.htm",
        ),
        allowed_domains=("www.nankai.edu.cn",),
        match_domains=("www.nankai.edu.cn",),
        include_patterns=(r"https?://(www\.)?nankai\.edu\.cn/.*",),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=14_000,
        priority=90,
        depth_limit=7,
        politeness_delay=0.8,
        concurrency_per_domain=2,
    ),
    CrawlSection(
        key="schools",
        label="院系学科",
        category="院系学科",
        description="学院官网、教师队伍、科研方向、招生培养、学术活动等。",
        seed_urls=(
            "https://cs.nankai.edu.cn/",
            "https://math.nankai.edu.cn/",
            "https://physics.nankai.edu.cn/",
            "https://chem.nankai.edu.cn/",
            "https://sky.nankai.edu.cn/",
            "https://env.nankai.edu.cn/",
            "https://law.nankai.edu.cn/",
            "https://economics.nankai.edu.cn/",
            "https://bs.nankai.edu.cn/",
            "https://history.nankai.edu.cn/",
            "https://ceo.nankai.edu.cn/",
            "https://sfs.nankai.edu.cn/",
            "https://wxy.nankai.edu.cn/",
            "https://ic.nankai.edu.cn/",
            "https://zfxy.nankai.edu.cn/",
            "https://cz.nankai.edu.cn/",
            "https://tas.nankai.edu.cn/",
            "https://taslab.nankai.edu.cn/",
            "https://phil.nankai.edu.cn/",
            "https://art.nankai.edu.cn/",
            "https://ai.nankai.edu.cn/",
            "https://medical.nankai.edu.cn/",
            "https://pharmacy.nankai.edu.cn/",
            "https://finance.nankai.edu.cn/",
            "https://stat.nankai.edu.cn/",
            "https://hyxy.nankai.edu.cn/",
        ),
        allowed_domains=(
            "cs.nankai.edu.cn",
            "math.nankai.edu.cn",
            "physics.nankai.edu.cn",
            "chem.nankai.edu.cn",
            "sky.nankai.edu.cn",
            "env.nankai.edu.cn",
            "law.nankai.edu.cn",
            "economics.nankai.edu.cn",
            "bs.nankai.edu.cn",
            "history.nankai.edu.cn",
            "ceo.nankai.edu.cn",
            "sfs.nankai.edu.cn",
            "wxy.nankai.edu.cn",
            "ic.nankai.edu.cn",
            "zfxy.nankai.edu.cn",
            "cz.nankai.edu.cn",
            "tas.nankai.edu.cn",
            "taslab.nankai.edu.cn",
            "phil.nankai.edu.cn",
            "art.nankai.edu.cn",
            "ai.nankai.edu.cn",
            "medical.nankai.edu.cn",
            "pharmacy.nankai.edu.cn",
            "finance.nankai.edu.cn",
            "stat.nankai.edu.cn",
            "hyxy.nankai.edu.cn",
        ),
        match_domains=(
            "cs.nankai.edu.cn",
            "math.nankai.edu.cn",
            "physics.nankai.edu.cn",
            "chem.nankai.edu.cn",
            "sky.nankai.edu.cn",
            "env.nankai.edu.cn",
            "law.nankai.edu.cn",
            "economics.nankai.edu.cn",
            "bs.nankai.edu.cn",
            "history.nankai.edu.cn",
            "ceo.nankai.edu.cn",
            "sfs.nankai.edu.cn",
            "wxy.nankai.edu.cn",
            "ic.nankai.edu.cn",
            "zfxy.nankai.edu.cn",
            "cz.nankai.edu.cn",
            "tas.nankai.edu.cn",
            "taslab.nankai.edu.cn",
            "phil.nankai.edu.cn",
            "art.nankai.edu.cn",
            "ai.nankai.edu.cn",
            "medical.nankai.edu.cn",
            "pharmacy.nankai.edu.cn",
            "finance.nankai.edu.cn",
            "stat.nankai.edu.cn",
            "hyxy.nankai.edu.cn",
        ),
        include_patterns=(r"https?://[^/]*\.?(cs|math|physics|chem|sky|env|law|economics|bs|history|ceo|sfs|wxy|ic|zfxy|cz|tas|taslab|phil|art|ai|medical|pharmacy|finance|stat|hyxy)\.nankai\.edu\.cn/.*",),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=42_000,
        priority=80,
        depth_limit=8,
        politeness_delay=0.9,
        concurrency_per_domain=2,
    ),
    CrawlSection(
        key="academic",
        label="教学招生",
        category="教学招生",
        description="教务、研究生院、招生办公室、课程通知、培养方案和考试信息。",
        seed_urls=(
            "https://jwc.nankai.edu.cn/",
            "https://graduate.nankai.edu.cn/",
            "https://jgs.graduate.nankai.edu.cn/",
            "https://yzb.nankai.edu.cn/",
            "https://zsb.nankai.edu.cn/"
        ),
        allowed_domains=(
            "jwc.nankai.edu.cn",
            "graduate.nankai.edu.cn",
            "jgs.graduate.nankai.edu.cn",
            "yzb.nankai.edu.cn",
            "zsb.nankai.edu.cn"
        ),
        match_domains=(
            "jwc.nankai.edu.cn",
            "graduate.nankai.edu.cn",
            "jgs.graduate.nankai.edu.cn",
            "yzb.nankai.edu.cn",
            "zsb.nankai.edu.cn"
        ),
        include_patterns=(
            r"https?://(jwc|graduate|jgs\.graduate|yzb|zsb)\.nankai\.edu\.cn/.*",
        ),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=26_000,
        priority=75,
        depth_limit=8,
        politeness_delay=0.9,
        concurrency_per_domain=2,
        document_first=True,
    ),
    CrawlSection(
        key="research",
        label="科研平台",
        category="科研学术",
        description="科研部门、实验室、学术活动、科研项目和成果信息。",
        seed_urls=(
            "https://std.nankai.edu.cn/",
            "https://std.nankai.edu.cn/main.htm",
            "https://ssrm.nankai.edu.cn/"
        ),
        allowed_domains=(
            "std.nankai.edu.cn",
            "ssrm.nankai.edu.cn"
        ),
        match_domains=(
            "std.nankai.edu.cn",
            "ssrm.nankai.edu.cn"
        ),
        include_patterns=(
            r"https?://(std|ssrm)\.nankai\.edu\.cn/.*",
        ),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=18_000,
        priority=70,
        depth_limit=7,
        politeness_delay=0.9,
        concurrency_per_domain=2,
        document_first=True,
    ),
    CrawlSection(
        key="library",
        label="图书资源",
        category="图书资源",
        description="图书馆、数据库、电子资源、检索指南、学位论文和读者服务。",
        seed_urls=(
            "https://lib.nankai.edu.cn/",
            "https://lib.nankai.edu.cn/main.htm",
            "https://www.lib.nankai.edu.cn/",
            "https://paper.lib.nankai.edu.cn/"
        ),
        allowed_domains=(
            "lib.nankai.edu.cn",
            "www.lib.nankai.edu.cn",
            "paper.lib.nankai.edu.cn"
        ),
        match_domains=(
            "lib.nankai.edu.cn",
            "www.lib.nankai.edu.cn",
            "paper.lib.nankai.edu.cn"
        ),
        include_patterns=(
            r"https?://(www\.)?lib\.nankai\.edu\.cn/.*", r"https?://paper\.lib\.nankai\.edu\.cn/.*"
        ),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=8_000,
        priority=65,
        depth_limit=7,
        politeness_delay=0.9,
        concurrency_per_domain=2,
        document_first=True,
    ),
    CrawlSection(
        key="anime",
        label="南开动漫",
        category="动漫资源",
        description="南开动漫资源站、社团内容、番剧资源、活动信息和资源站页面。",
        seed_urls=(
            "http://12club.nankai.edu.cn/",
            "http://12club.nankai.edu.cn/anime",
            "http://12club.nankai.edu.cn/comic",
            "http://12club.nankai.edu.cn/game",
            "http://12club.nankai.edu.cn/novel",
        ),
        allowed_domains=("12club.nankai.edu.cn",),
        match_domains=("12club.nankai.edu.cn",),
        include_patterns=(r"https?://12club\.nankai\.edu\.cn/.*",),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=12_000,
        priority=62,
        depth_limit=7,
        politeness_delay=1.0,
        concurrency_per_domain=1,
    ),
    CrawlSection(
        key="services",
        label="校园服务",
        category="校园服务",
        description="信息化服务、网络服务、校园账号和生活服务信息。",
        seed_urls=(
            "https://wxb.nankai.edu.cn/",
            "https://rsc.nankai.edu.cn/",
            "https://xxgk.nankai.edu.cn/",
            "https://nkuaa.nankai.edu.cn/",
            "https://xcb.nankai.edu.cn/",
            "https://zzb.nankai.edu.cn/",
            "https://xb.nankai.edu.cn/",
            "https://cwc.nankai.edu.cn/",
            "https://international.nankai.edu.cn/",
            "https://en.nankai.edu.cn/"
        ),
        allowed_domains=(
            "wxb.nankai.edu.cn",
            "rsc.nankai.edu.cn",
            "xxgk.nankai.edu.cn",
            "nkuaa.nankai.edu.cn",
            "xcb.nankai.edu.cn",
            "zzb.nankai.edu.cn",
            "xb.nankai.edu.cn",
            "cwc.nankai.edu.cn",
            "international.nankai.edu.cn",
            "en.nankai.edu.cn"
        ),
        match_domains=(
            "wxb.nankai.edu.cn",
            "rsc.nankai.edu.cn",
            "xxgk.nankai.edu.cn",
            "nkuaa.nankai.edu.cn",
            "xcb.nankai.edu.cn",
            "zzb.nankai.edu.cn",
            "xb.nankai.edu.cn",
            "cwc.nankai.edu.cn",
            "international.nankai.edu.cn",
            "en.nankai.edu.cn"
        ),
        include_patterns=(
            r"https?://(wxb|rsc|xxgk|nkuaa|xcb|zzb|xb|cwc|international|en)\.nankai\.edu\.cn/.*",
        ),
        deny_patterns=COMMON_DENY_PATTERNS,
        max_pages=4_000,
        priority=60,
        depth_limit=6,
        politeness_delay=1.0,
        concurrency_per_domain=1,
    ),
)

SECTION_BY_KEY = {section.key: section for section in CRAWL_SECTIONS}
TOTAL_TARGET_PAGES = sum(section.max_pages for section in CRAWL_SECTIONS)


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def get_crawl_plan(section_keys: list[str] | tuple[str, ...] | None = None) -> list[CrawlSection]:
    if not section_keys:
        return list(CRAWL_SECTIONS)
    unknown = [key for key in section_keys if key not in SECTION_BY_KEY]
    if unknown:
        known = ", ".join(SECTION_BY_KEY)
        raise ValueError(f"Unknown crawl section(s): {', '.join(unknown)}. Known sections: {known}")
    return [SECTION_BY_KEY[key] for key in section_keys]


def seed_urls_for(section_keys: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for section in get_crawl_plan(section_keys):
        for url in section.seed_urls:
            seen.setdefault(url, None)
    return tuple(seen)


def allowed_domains_for(section_keys: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for section in get_crawl_plan(section_keys):
        for domain in section.allowed_domains:
            seen.setdefault(domain, None)
    return tuple(seen)


def section_budgets_for(section_keys: list[str] | tuple[str, ...] | None = None, scale_factor: float = 1.0) -> dict[str, int]:
    factor = max(scale_factor, 0.01)
    return {section.key: max(int(section.max_pages * factor), 1) for section in get_crawl_plan(section_keys)}


def section_for_url(url: str) -> CrawlSection:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    path = urlparse(url).path.lower()
    suffix = Path(path).suffix.lstrip(".")

    for section in CRAWL_SECTIONS:
        if any(_host_matches(host, domain) for domain in section.match_domains):
            return section

    if host == "nankai.edu.cn":
        return SECTION_BY_KEY["main"]
    if suffix in DOCUMENT_EXTENSIONS:
        return SECTION_BY_KEY["academic"]
    return SECTION_BY_KEY["main"]


def crawl_plan_summary(section_keys: list[str] | tuple[str, ...] | None = None, scale_factor: float = 1.0) -> dict[str, object]:
    sections = get_crawl_plan(section_keys)
    budgets = section_budgets_for(section_keys, scale_factor=scale_factor)
    target_pages = sum(budgets.values())
    return {
        "minimum_pages": MIN_HOMEWORK_PAGES,
        "target_pages": target_pages,
        "scale_factor": scale_factor,
        "section_count": len(sections),
        "seed_count": sum(len(section.seed_urls) for section in sections),
        "sections": [
            {
                **section.to_public_dict(),
                "scaled_max_pages": budgets[section.key],
            }
            for section in sections
        ],
    }


def format_plan_table(section_keys: list[str] | tuple[str, ...] | None = None, scale_factor: float = 1.0) -> str:
    summary = crawl_plan_summary(section_keys, scale_factor=scale_factor)
    lines = [
        f"NKU crawl target: {summary['target_pages']} pages (homework minimum: {MIN_HOMEWORK_PAGES})",
        "",
        "key          category    target   delay  conc  seeds  label",
        "-----------  ----------  -------  -----  ----  -----  ----------------",
    ]
    for section in summary["sections"]:
        lines.append(
            f"{section['key']:<11}  {section['category']:<10}  "
            f"{section['scaled_max_pages']:>7}  {section['politeness_delay']:>5}  "
            f"{section['concurrency_per_domain']:>4}  {section['seed_count']:>5}  {section['label']}"
        )
    return "\n".join(lines)
