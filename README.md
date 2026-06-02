# NKU Search

南开校内资源搜索引擎课程项目，覆盖网页抓取、文本索引、搜索排序、个性化、联想推荐和单端口 Web 界面。项目采用工程化实现，核心技术栈为：

```text
Scrapy + Elasticsearch + FastAPI + SQLite + React + Vite + Ant Design
```

项目参考 Scrapy、Whoosh、FastAPI Full Stack Template、Ant Design Pro、Elastic Search UI、Haystack、Meilisearch 的架构思想，并在本仓库内完成改写和集成。参考仓库目录 `references/`、虚拟环境、真实爬取数据、快照和 Elasticsearch 数据卷不会提交到 Git。

## 功能

- 大规模爬虫：Scrapy CrawlSpider、robots、AutoThrottle、HTTP cache、JOBDIR 断点续爬、按主题预算抓取。
- 多来源覆盖：南开主站、新闻站、学院站、教学招生、科研学术、图书资源、动漫资源和校园服务。
- 文本索引：HTML、PDF、DOC、DOCX、XLS、XLSX、PPT、PPTX、标题、正文、URL、锚文本、文件类型、主题、PageRank、网页快照。
- 搜索服务：Elasticsearch 后端，ES 不可用时使用本地 BM25F 倒排索引兜底。
- 查询能力：普通查询、站内查询、文档查询、短语查询、通配查询、正则查询、查询日志和网页快照。
- 个性化：注册、登录、兴趣词、查询历史、点击日志、个性化排序 boost。
- 推荐：搜索框联想，来源包括历史查询、索引高频标题词和用户个人历史。
- Web 界面：React + Ant Design 控制台，包含搜索、主题、文档、历史、账号、分面筛选、分页和推荐。

## 快速启动

Windows CMD 或 PowerShell 均可。第一次 clone 后先安装依赖：

```bat
cd /d D:\hw4
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm.cmd install --cache ..\.npm-cache
cd ..
```

启动 Elasticsearch 和单端口 Web 服务：

```bat
cd /d D:\hw4
docker compose up -d elasticsearch
.\.venv\Scripts\python.exe -B -m nku_search.serve --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000
```

`nku_search.serve` 会检测 `frontend/dist` 是否过期，必要时自动执行 `npm run build`。前端静态文件和后端 API 都由 FastAPI 在 `8000` 端口提供。

## 健康检查

```bat
curl http://127.0.0.1:8000/health
```

返回示例：

```json
{"status":"ok","backend":"SearchBackend","elasticsearch":true,"index":"nku_pages","documents":135779}
```

- `SearchBackend`：正在使用 Elasticsearch。
- `LocalSearchBackend`：ES 未启动、索引为空，或 9200 不可访问。此时系统会使用内置样例 `nku_search/fixtures/sample_documents.jsonl`。

## 建立索引

仓库不提交真实 `data/` 目录。首次 clone 后可以先用内置样例建立小索引：

```bat
docker compose up -d elasticsearch
.\.venv\Scripts\python.exe -B -m nku_search.index --reset
```

如果本机已有真实爬取结果，将 JSONL 放在 `data/crawl/` 后执行：

```bat
.\.venv\Scripts\python.exe -B -m nku_search.index --input data/crawl/pages_160k_clean.jsonl --reset
```

索引阶段会计算 PageRank、写入 Elasticsearch、保存快照到 `data/snapshots/`，并把联想词写入 SQLite。

## 爬取命令

查看 16 万页默认主题计划：

```bat
.\.venv\Scripts\python.exe -B -m nku_search.crawl --list-sections
```

执行完整高价值抓取：

```bat
.\.venv\Scripts\python.exe -B -m nku_search.crawl --max-pages 160000 --output data/crawl/pages_160k.jsonl
```

清洗数据：

```bat
.\.venv\Scripts\python.exe -B -m nku_search.clean --input data/crawl/pages_160k.jsonl --output data/crawl/pages_160k_clean.jsonl
```

默认板块预算：

| Section | 主题 | 目标页数 |
|---|---|---:|
| news | 新闻资讯 | 36000 |
| main | 学校门户 | 14000 |
| schools | 院系学科 | 42000 |
| academic | 教学招生 | 26000 |
| research | 科研学术 | 18000 |
| library | 图书资源 | 8000 |
| anime | 动漫资源 | 12000 |
| services | 校园服务 | 4000 |

## 查询语法

| 类型 | 示例 | 说明 |
|---|---|---|
| 普通查询 | `南开 大学` | 关键词相关性检索 |
| 短语查询 | `"南开大学"` 或 `“南开大学”` | 固定顺序连续匹配 |
| 站内查询 | `site:news.nankai.edu.cn 南开` | 限定域名或 URL 前缀 |
| 文档查询 | `filetype:pdf CARSI` | 限定文件类型 |
| 标题查询 | `title:人工智能 南开` | 提升标题命中 |
| URL 查询 | `inurl:graduate 招生` | URL 包含指定片段 |
| 通配查询 | `南开*`、`计?` | `*` 多字符，`?` 单字符 |
| 正则查询 | `/南.*/` | 正则匹配标题或正文 token |

## API

- `GET /api/search`
- `GET /api/suggest`
- `GET /api/topics`
- `GET /api/stats`
- `GET /api/crawl-plan`
- `GET /api/history`
- `GET /api/pipeline`
- `GET /api/references`
- `POST /api/register`
- `POST /api/login`
- `POST /api/profile`
- `POST /api/click`
- `GET /snapshot/{doc_id}`
- `GET /health` / `GET /api/health`

## 项目结构

```text
nku_search/
  crawler_project/       Scrapy 工程化爬虫
  fixtures/              可提交的小型测试样例
  advanced_query.py      高级查询解析
  query.py               查询模式识别和 ES 查询构建
  search_engine.py       Elasticsearch 后端和本地后端
  local_index.py         本地 BM25F 倒排索引
  index.py               JSONL -> PageRank -> Elasticsearch
  web.py                 FastAPI API、账号、日志、快照、静态前端托管
  serve.py               单端口启动器，自动检查前端构建
frontend/
  src/SearchConsole.tsx  React + Ant Design 搜索控制台
docs/                    说明文档、演示脚本、设计与验证材料
tests/                   单元测试和接口测试
docker-compose.yml       Elasticsearch 8.15.1
```

## 测试

```bat
.\.venv\Scripts\python.exe -B -m pytest
cd frontend
npm.cmd run build
cd ..
```

当前验证记录：Python 测试 `67 passed, 3 warnings`；真实 Elasticsearch 索引 `nku_pages` 已验证 `135779` 条文档；普通查询、短语查询、站内查询、文档查询、通配查询、正则查询、登录注册、历史、点击日志、网页快照和联想推荐均可用。

## Git 忽略策略

`.gitignore` 已排除：

- `.venv/`、`.uv-cache/`、`.npm-cache/`
- `frontend/node_modules/`、`frontend/dist/`
- `data/`、`elasticsearch-data/`
- `references/`
- `dist/`、`build/`
- `.env`、日志、SQLite 数据库和缓存目录

