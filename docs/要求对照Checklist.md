# 作业要求逐项对照 Checklist

> 状态日期：2026-06-01。暂不检查打包提交项。

## 1. 作业目标

| 要求 | 状态 | 对应实现 |
|---|---|---|
| 面向南开校内资源构建 Web 搜索引擎 | 已完成 | `nku_search/crawl_plan.py` 定义新闻、主站、院系、教学招生、科研、图书、动漫、校园服务 8 个板块；`frontend/src/SearchConsole.tsx` 提供统一搜索入口 |
| 为用户提供查询服务和个性化推荐 | 已完成 | `nku_search/web.py` 的 `/api/search`、`/api/suggest`、`/api/history`；`nku_search/storage.py` 用户/历史/联想表；`nku_search/recommend.py` |
| 可借助工具和包，推荐 Elasticsearch | 已完成 | `docker-compose.yml`、`nku_search/search_engine.py`；ES 不可用时 `LocalSearchBackend` 自动兜底 |

## 2.1 网页抓取

| 要求 | 状态 | 对应实现/验证 |
|---|---|---|
| 抓取南开校内资源 | 已完成 | `nku_search/crawler_project/spiders/nku_crawl.py`，`nku_search/crawl_plan.py` |
| 抓取数量至少 100000 页 | 已完成 | `data/crawl/pages_160k_clean.jsonl` 有 135779 条有效记录，0 条无效 |
| 礼貌抓取、遵守爬虫协议 | 已完成 | Scrapy settings：`ROBOTSTXT_OBEY=True` 在 `nku_search/crawler_project/settings.py`；AutoThrottle、下载延迟、每域并发在 `nku_search/crawl.py` |
| 支持续爬 | 已完成 | Scrapy `JOBDIR`、`existing_output_counts()`、`existing_output_urls()`、高价值 jobdir：`nku_search/crawler_project/pipelines.py`、`nku_search/crawl.py` |
| 覆盖动漫资源站 | 已完成 | `anime` 板块包含 `12club.nankai.edu.cn`；专门解析 Next.js action：`_schedule_12club_resource_frontier()` |

当前数据分布：schools 73253、main 27161、academic 13114、services 7396、news 5724、research 5159、library 2456、anime 1516。

## 2.2 文本索引

| 要求 | 状态 | 对应实现/验证 |
|---|---|---|
| 对网页文本构建索引 | 已完成 | `nku_search/index.py`、`nku_search/search_engine.py`、`nku_search/local_index.py` |
| 支持多个索引域：标题、URL、锚文本等 | 已完成 | ES mapping：`title/text/anchors/url/filetype/section/category/pagerank`；本地 schema：`nku_search/schema.py` |
| 支持 HTML 附件文本 | 已完成 | `nku_search/text.py` 的 `html_to_text()`、`extract_document_text()` |
| 支持 PDF/DOC/DOCX/XLS/XLSX/PPT/PPTX 等文档 | 已完成 | `pdfplumber`、`python-docx`、`openpyxl`、PPTX XML 解析与旧 PPT 安全标题清洗；当前 ES filetypes：html 126131、pdf 4846、doc 2096、docx 1436、xlsx 763、xls 493、ppt 6、pptx 6、txt 2 |
| 保存网页快照 | 已完成 | `nku_search/index.py::save_snapshot()`；当前 `data/snapshots` 有 135781 个快照文件 |

## 2.3 查询服务

| 要求 | 状态 | 对应实现/验证 |
|---|---|---|
| 基于向量空间模型排序 | 已完成 | `nku_search/text.py` 的 TF/IDF + cosine；`nku_search/ranking.py` 的 `score_document()`；`nku_search/scoring.py` 的 BM25F |
| 结合链接分析排序 | 已完成 | `nku_search/ranking.py::compute_pagerank()`；索引阶段写入 `pagerank`；ES 查询用 `field_value_factor` 融合 PageRank |
| 提供 Web/API 查询服务 | 已完成 | FastAPI：`nku_search/web.py`；前端：`frontend/src/SearchConsole.tsx` |
| 返回分页结果 | 已完成 | `SearchQuery.page/size/offset`、ES `from/size`、前端 `Pagination`；已修复最后一页 500 |
| 返回分面筛选 | 已完成 | Local facets：`LocalInvertedIndex.facets()`；ES aggs：`build_es_query()` + `SearchBackend._facets_from_response()` |

### 六类高级搜索功能

| 功能 | 状态 | 对应实现/验证 |
|---|---|---|
| 站内查询 | 已完成 | `site` 参数、`site:` 高级语法和站点分面；`query.py` prefix filter；接口验证 200 |
| 文档查询 | 已完成 | `filetype` 参数和 `filetype:` 语法；前端“文档”页；接口验证 PDF 200 |
| 短语查询 | 已完成 | `mode=phrase` 与双引号检测；带引号短语可与 `site:` 等高级语法组合；`multi_match type=phrase`；接口验证 200 |
| 通配查询 | 已完成 | `mode=wildcard`、`*`、`?`；`wildcard_to_regex()` 和 ES wildcard；接口验证 200 |
| 正则查询 | 已完成 | `mode=regex`、`/pattern/`；ES regexp、本地 `re.search()`；接口验证 200 |
| 查询日志 | 已完成 | SQLite `query_logs`；`/api/history`、`/history`、前端历史页；接口验证 200 |
| 网页快照 | 已完成 | `/snapshot/{doc_id}`；索引阶段保存 HTML/文本快照；接口验证 200 |

## 2.4 个性化查询

| 要求 | 状态 | 对应实现/验证 |
|---|---|---|
| 注册/登录系统 | 已完成 | `nku_search/auth.py`、`nku_search/storage.py`、`/api/register`、`/api/login`、前端账号页 |
| 不同用户有不同排序依据 | 已完成 | `Storage.user_query_terms()` 现在合并注册兴趣词和用户查询历史；ES 通过 `should` boost，本地通过 `infer_interest_score()` |
| 点击和搜索历史 | 已完成 | `query_logs`、`click_logs`；`/api/click`；前端结果点击自动记录 |

## 2.5 Web 界面

| 要求 | 状态 | 对应实现 |
|---|---|---|
| Web Page 或 Terminal 均可 | 已完成 | Web：React + Ant Design；CLI：crawl/index/serve/diagnose/analytics |
| 搜索首页 | 已完成 | `/` 托管 `frontend/dist`，无前后端分端口 |
| 搜索、主题、文档、历史、账号功能 | 已完成 | `frontend/src/SearchConsole.tsx`；前端仅展示中文主题筛选，`section` 保留为内部爬虫/索引字段 |
| 后端模板兜底 | 已完成 | `nku_search/templates/*.html` |

## 2.6 个性化推荐

| 要求 | 状态 | 对应实现/验证 |
|---|---|---|
| 搜索联想关联 | 已完成 | `/api/suggest`；`suggestions` 表；索引高频词、匿名全局查询、登录用户个人历史；登录用户查询词不会污染游客推荐 |
| 内容分析后的推荐（二选一即可） | 已覆盖一部分 | `extract_suggestion_terms()` 从标题和正文提取高频词写入联想表 |

## 3. 评分材料

| 要求 | 状态 | 对应文件 |
|---|---|---|
| 说明文档 | 已完成 | `docs/说明文档.md`、`docs/大规模爬取计划.md`、`docs/运行分析报告.md`、`docs/数据清洗报告.md` |
| 演示视频脚本 | 已完成 | `docs/演示视频脚本.md` |
| 打包提交 | 暂不处理 | 用户要求“先不用打包作业” |

## 演示视频覆盖核对

| 作业要求 | 视频脚本覆盖位置 |
|---|---|
| 项目目标与南开资源搜索主题 | 1 开场介绍 |
| Scrapy 网页抓取、10 万页以上、robots、续爬、动漫站 | 4 爬虫设计与抓取计划 |
| Elasticsearch 与大规模索引 | 0.3 快速健康检查、3 数据规模与 Elasticsearch |
| 文本索引、多字段、文档解析、快照 | 1 开场介绍、3 数据规模、7.2 文档查询、7.7 网页快照 |
| 向量空间/文本相关性排序与 PageRank | 5 综合搜索与分页 |
| Web/API 查询服务和分页 | 5 综合搜索与分页、10 API 与后端能力 |
| 分面筛选 | 6 分面筛选 |
| 站内查询 | 7.1 站内查询 |
| 文档查询 | 7.2 文档查询 |
| 短语查询 | 7.3 短语查询 |
| 通配查询 | 7.4 通配查询 |
| 正则查询 | 7.5 正则查询 |
| 查询日志 | 7.6 查询日志 |
| 网页快照 | 7.7 网页快照 |
| 注册登录、兴趣词、个性化排序、点击日志 | 8 个性化查询 |
| 搜索联想/个性化推荐 | 9 搜索联想推荐 |
| 说明文档和测试验证 | 2 项目结构与完成度、11 测试与验证 |
| 打包提交 | 暂不处理，视频明确说明当前不演示打包 |

## 本次验证记录

- Python 测试：`67 passed, 3 warnings`。
- 前端构建：`npm.cmd run build` 通过。
- Elasticsearch：Docker Desktop 启动后已验证，集群 `green`，`nku_pages` 文档数 `135779`，`max_result_window=200000`。`/health` 返回 `SearchBackend`。
- JSONL 数据：`data/crawl/pages_160k_clean.jsonl` 有 135779 条有效记录。
- 快照：`data/snapshots` 有 135781 个文件。
- 真实 ES 接口验证：普通搜索 `南开` 返回 `86247` 条、最后页 `7` 条、站内查询 `site:news.nankai.edu.cn 南开` 返回 `5723` 条、PDF 文档全库 `4846` 条、短语 `"南开大学"` 返回 `80371` 条、通配 `南开*` 返回 `40414` 条、正则 `/南.*/` 返回 `85045` 条、动漫主题返回 `1513` 条，联想、注册登录、个性化搜索、历史、点击日志、快照均返回 200。

## 当前非代码阻塞项

- 暂不处理打包提交项；用户要求“先不用打包作业”。
- Docker Desktop 当前已启动，Elasticsearch 真实后端已验证可用。后续如重启机器，只需执行：

```powershell
docker compose up -d elasticsearch
.\.venv\Scripts\python.exe -B -m nku_search.serve --host 127.0.0.1 --port 8000
```


