from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import html
import os
from pathlib import Path

from .auth import AuthService
from .config import ROOT_DIR, SAMPLE_DOCUMENTS_PATH, STATIC_DIR, TEMPLATE_DIR, ensure_data_dirs, get_settings
from .crawl_plan import crawl_plan_summary
from .index import load_pages
from .query import SearchQuery, detect_mode
from .recommend import update_suggestions_from_query
from .search_engine import LocalSearchBackend, SearchBackend
from .search_pipeline import SearchPipeline
from .storage import Storage

try:
    from fastapi import Cookie, FastAPI, Form, Query, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel
except Exception as exc:  # pragma: no cover - import-time guard for environments without deps.
    raise RuntimeError("FastAPI dependencies are missing. Run: pip install -r requirements.txt") from exc


class LoginPayload(BaseModel):
    username: str
    password: str


class RegisterPayload(BaseModel):
    username: str
    password: str
    interests: str = ""


class ProfilePayload(BaseModel):
    interests: str = ""


class ClickPayload(BaseModel):
    doc_id: str
    url: str
    title: str = ""


FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"


def frontend_shell() -> HTMLResponse:
    return HTMLResponse(
        FRONTEND_INDEX.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


def _small_local_index_path() -> Path:
    settings = get_settings()
    max_bytes = int(os.getenv("NKU_LOCAL_INDEX_MAX_BYTES", str(200 * 1024 * 1024)))
    for path in (settings.clean_crawl_output, settings.crawl_output):
        if path.exists() and path.stat().st_size <= max_bytes:
            return path
    return SAMPLE_DOCUMENTS_PATH


def _elasticsearch_backend_if_ready() -> SearchBackend | None:
    settings = get_settings()
    backend = SearchBackend(settings.elasticsearch_url, settings.index_name)
    if backend.ping():
        try:
            exists = backend.client.indices.exists(index=backend.index_name)
            count = int(backend.client.count(index=backend.index_name).get("count", 0)) if exists else 0
            if count > 0:
                return backend
        except Exception:
            pass
    return None


def choose_backend() -> SearchBackend | LocalSearchBackend:
    backend = _elasticsearch_backend_if_ready()
    if backend is not None:
        return backend
    return LocalSearchBackend(load_pages(_small_local_index_path()))


class BackendManager:
    def __init__(self) -> None:
        self._backend: SearchBackend | LocalSearchBackend = choose_backend()

    def get(self) -> SearchBackend | LocalSearchBackend:
        if isinstance(self._backend, LocalSearchBackend):
            backend = _elasticsearch_backend_if_ready()
            if backend is not None:
                self._backend = backend
        return self._backend


def backend_status(backend: SearchBackend | LocalSearchBackend) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok",
        "backend": backend.__class__.__name__,
    }
    if isinstance(backend, SearchBackend):
        count = 0
        es_ok = backend.ping()
        if es_ok:
            try:
                count = int(backend.client.count(index=backend.index_name).get("count", 0))
            except Exception:
                count = 0
        payload.update(
            {
                "elasticsearch": es_ok,
                "index": backend.index_name,
                "documents": count,
            }
        )
    else:
        payload.update(
            {
                "elasticsearch": False,
                "index": get_settings().index_name,
                "documents": len(backend.pages),
            }
        )
    return payload


def current_user(storage: Storage, session: str | None) -> dict | None:
    user = storage.get_user_by_session(session)
    return dict(user) if user else None


def topic_payload(backend: SearchBackend | LocalSearchBackend) -> dict[str, object]:
    plan = crawl_plan_summary()
    local_index = getattr(backend, "index", None)
    section_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    if local_index is not None:
        for page in local_index.pages:
            section_counts[page.section] += 1
            category_counts[page.category] += 1
    else:
        try:
            response = backend.client.search(
                index=backend.index_name,
                body={
                    "size": 0,
                    "aggs": {
                        "section": {"terms": {"field": "section", "size": 32}},
                        "category": {"terms": {"field": "category", "size": 32}},
                    },
                },
            )
            for bucket in response.get("aggregations", {}).get("section", {}).get("buckets", []):
                section_counts[str(bucket.get("key", ""))] = int(bucket.get("doc_count", 0))
            for bucket in response.get("aggregations", {}).get("category", {}).get("buckets", []):
                category_counts[str(bucket.get("key", ""))] = int(bucket.get("doc_count", 0))
        except Exception:
            pass

    sections: list[dict[str, object]] = []
    for section in plan["sections"]:
        key = str(section["key"])
        count = section_counts.get(key, 0)
        target = int(section.get("scaled_max_pages", section.get("max_pages", 1)) or 1)
        sections.append(
            {
                **section,
                "indexed_count": count,
                "indexed_progress": round(min(count / max(target, 1), 1.0), 4),
            }
        )
    return {
        "minimum_pages": plan["minimum_pages"],
        "target_pages": plan["target_pages"],
        "section_count": plan["section_count"],
        "seed_count": plan["seed_count"],
        "sections": sections,
        "categories": [
            {"name": name, "indexed_count": count}
            for name, count in category_counts.most_common()
        ],
    }


def create_app() -> FastAPI:
    ensure_data_dirs()
    settings = get_settings()
    storage = Storage()
    auth = AuthService(storage)
    backend_manager = BackendManager()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    def active_backend() -> SearchBackend | LocalSearchBackend:
        return backend_manager.get()

    app = FastAPI(title="NKU Web Search Engine", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if FRONTEND_ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS)), name="frontend-assets")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, session: str | None = Cookie(default=None)):
        if FRONTEND_INDEX.exists():
            return frontend_shell()
        backend = active_backend()
        user = current_user(storage, session)
        suggestions = storage.suggestions("", limit=8, user_id=user["id"] if user else None)
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "user": user, "suggestions": suggestions, "backend": backend.__class__.__name__},
        )

    @app.get("/search", response_class=HTMLResponse)
    def search_page(
        request: Request,
        q: str = Query(default=""),
        site: str = Query(default=""),
        filetype: str = Query(default=""),
        section: str = Query(default=""),
        category: str = Query(default=""),
        mode: str = Query(default=""),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=50),
        session: str | None = Cookie(default=None),
    ):
        if FRONTEND_INDEX.exists():
            return frontend_shell()
        backend = active_backend()
        user = current_user(storage, session)
        search = SearchQuery(
            q=q,
            mode=detect_mode(q, mode or None),
            site=site or None,
            filetype=filetype or None,
            section=section or None,
            category=category or None,
            page=page,
            size=size,
        )
        user_terms = storage.user_query_terms(user["id"] if user else None)
        hits, total = backend.search(search, user_terms=user_terms)
        diagnostics = getattr(backend, "last_diagnostics", None) or getattr(getattr(backend, "index", None), "last_diagnostics", None)
        storage.log_query(q, str(search.mode), total, user_id=user["id"] if user else None, site=site or None, filetype=filetype or None)
        update_suggestions_from_query(storage, q, user_id=user["id"] if user else None)
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "user": user,
                "query": search,
                "hits": hits,
                "total": total,
                "page": page,
                "backend": backend.__class__.__name__,
                "diagnostics": diagnostics,
            },
        )

    @app.get("/api/search")
    def api_search(
        q: str = Query(default=""),
        site: str = Query(default=""),
        filetype: str = Query(default=""),
        section: str = Query(default=""),
        category: str = Query(default=""),
        mode: str = Query(default=""),
        page: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=50),
        session: str | None = Cookie(default=None),
    ):
        backend = active_backend()
        user = current_user(storage, session)
        search = SearchQuery(
            q=q,
            mode=detect_mode(q, mode or None),
            site=site or None,
            filetype=filetype or None,
            section=section or None,
            category=category or None,
            page=page,
            size=size,
        )
        hits, total = backend.search(search, user_terms=storage.user_query_terms(user["id"] if user else None))
        diagnostics = getattr(backend, "last_diagnostics", None) or getattr(getattr(backend, "index", None), "last_diagnostics", None)
        storage.log_query(q, str(search.mode), total, user_id=user["id"] if user else None, site=site or None, filetype=filetype or None)
        update_suggestions_from_query(storage, q, user_id=user["id"] if user else None)
        return {
            "query": q,
            "mode": str(search.mode),
            "total": total,
            "diagnostics": asdict(diagnostics) if diagnostics else None,
            "results": [asdict(hit) for hit in hits],
        }

    @app.get("/api/stats")
    def api_stats():
        backend = active_backend()
        local_index = getattr(backend, "index", None)
        if local_index is not None:
            facets = local_index.facets()
            return {
                "backend": backend.__class__.__name__,
                "documents": local_index.doc_count,
                "vocabulary": len(local_index.vocabulary),
                "schema": [asdict(field) for field in local_index.schema.fields],
                "facets": [asdict(facet) for facet in facets],
                "crawl_plan": topic_payload(backend),
                "diagnostics": asdict(local_index.last_diagnostics),
                "features": [
                    "BM25F",
                    "field boosts",
                    "facets",
                    "phrase search",
                    "wildcard search",
                    "query logs",
                    "snapshots",
                    "personalization",
                    "suggestions",
                    "section budgets",
                    "topic filters",
                ],
            }
        es_ok = False
        count = 0
        if isinstance(backend, SearchBackend):
            es_ok = backend.ping()
            if es_ok:
                count = int(backend.client.count(index=backend.index_name).get("count", 0))
        return {
            "backend": backend.__class__.__name__,
            "documents": count,
            "vocabulary": None,
            "elasticsearch": es_ok,
            "schema": [],
            "facets": [],
            "crawl_plan": topic_payload(backend),
            "features": ["Elasticsearch", "FastAPI", "SQLite"],
        }

    @app.get("/api/crawl-plan")
    def api_crawl_plan(scale_factor: float = Query(default=1.0, ge=0.01, le=20.0)):
        return crawl_plan_summary(scale_factor=scale_factor)

    @app.get("/api/topics")
    def api_topics():
        return topic_payload(active_backend())

    @app.get("/api/facets")
    def api_facets(
        q: str = Query(default=""),
        site: str = Query(default=""),
        filetype: str = Query(default=""),
        section: str = Query(default=""),
        category: str = Query(default=""),
        mode: str = Query(default=""),
        session: str | None = Cookie(default=None),
    ):
        backend = active_backend()
        user = current_user(storage, session)
        search = SearchQuery(
            q=q,
            mode=detect_mode(q, mode or None),
            site=site or None,
            filetype=filetype or None,
            section=section or None,
            category=category or None,
            page=1,
            size=10,
        )
        backend.search(search, user_terms=storage.user_query_terms(user["id"] if user else None))
        diagnostics = getattr(backend, "last_diagnostics", None) or getattr(getattr(backend, "index", None), "last_diagnostics", None)
        return {"facets": [asdict(facet) for facet in diagnostics.facets] if diagnostics else []}

    @app.get("/api/suggest")
    def api_suggest(q: str = Query(default=""), session: str | None = Cookie(default=None)):
        user = current_user(storage, session)
        return {"suggestions": storage.suggestions(q, limit=10, user_id=user["id"] if user else None)}

    @app.get("/api/me")
    def api_me(session: str | None = Cookie(default=None)):
        user = current_user(storage, session)
        if not user:
            return {"user": None}
        return {"user": {"id": user["id"], "username": user["username"], "interests": user["interests"]}}

    @app.post("/api/login")
    def api_login(payload: LoginPayload):
        ok, message, token = auth.login(payload.username, payload.password)
        response = JSONResponse({"ok": ok, "message": message})
        if not ok:
            return JSONResponse({"ok": False, "message": message}, status_code=401)
        if ok and token:
            response.set_cookie("session", token, httponly=True, samesite="lax")
        return response

    @app.post("/api/register")
    def api_register(payload: RegisterPayload):
        ok, message = auth.register(payload.username, payload.password, payload.interests)
        if not ok:
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        _, _, token = auth.login(payload.username, payload.password)
        response = JSONResponse({"ok": True, "message": message})
        if token:
            response.set_cookie("session", token, httponly=True, samesite="lax")
        return response

    @app.post("/api/profile")
    def api_profile(payload: ProfilePayload, session: str | None = Cookie(default=None)):
        user = current_user(storage, session)
        if not user:
            return JSONResponse({"ok": False, "message": "请先登录"}, status_code=401)
        interests = " ".join(payload.interests.split())
        storage.update_user_interests(int(user["id"]), interests)
        return {
            "ok": True,
            "message": "已更新兴趣词",
            "user": {"id": user["id"], "username": user["username"], "interests": interests},
        }

    @app.post("/api/logout")
    def api_logout(session: str | None = Cookie(default=None)):
        storage.delete_session(session)
        response = JSONResponse({"ok": True})
        response.delete_cookie("session")
        return response

    @app.get("/api/history")
    def api_history(session: str | None = Cookie(default=None), all_users: bool = Query(default=False)):
        user = current_user(storage, session)
        rows = storage.query_history(None if all_users or not user else user["id"], limit=100)
        return {
            "rows": [
                {
                    "id": row["id"],
                    "query": row["query"],
                    "mode": row["mode"],
                    "site": row["site"],
                    "filetype": row["filetype"],
                    "result_count": row["result_count"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        }

    @app.post("/api/click")
    def api_click(payload: ClickPayload, session: str | None = Cookie(default=None)):
        user = current_user(storage, session)
        storage.log_click(payload.doc_id, payload.url, payload.title, user_id=user["id"] if user else None)
        return {"ok": True}

    @app.get("/api/references")
    def api_references():
        return {
            "references": [
                {
                    "name": "Scrapy",
                    "path": "references/scrapy",
                    "used_for": "crawler settings/items/pipelines/CrawlSpider/Rule structure",
                },
                {
                    "name": "Whoosh",
                    "path": "references/whoosh",
                    "used_for": "schema/query parser/scoring/searcher separation",
                },
                {
                    "name": "FastAPI Full Stack Template",
                    "path": "references/full-stack-fastapi-template",
                    "used_for": "API-first backend/frontend split and JSON service style",
                },
                {
                    "name": "Ant Design Pro",
                    "path": "references/ant-design-pro",
                    "used_for": "dashboard layout, enterprise search UI, tables, cards and diagnostics views",
                },
                {
                    "name": "Elastic Search UI",
                    "path": "references/search-ui",
                    "used_for": "SearchProvider, connector, facets, paging and search state management",
                },
                {
                    "name": "Haystack",
                    "path": "references/haystack",
                    "used_for": "component pipeline design for query normalization, retrieval and suggestion building",
                },
                {
                    "name": "Meilisearch",
                    "path": "references/meilisearch",
                    "used_for": "search engine task/status and index settings reference; license constraints documented",
                },
            ]
        }

    @app.get("/api/pipeline")
    def api_pipeline():
        return SearchPipeline().describe()

    @app.get("/snapshot/{doc_id}", response_class=HTMLResponse)
    def snapshot(doc_id: str):
        backend = active_backend()
        for page in getattr(backend, "pages", []):
            if page.doc_id == doc_id:
                if page.html:
                    return HTMLResponse(page.html)
                title = html.escape(page.title)
                text = html.escape(page.text)
                return HTMLResponse(
                    f"<!doctype html><meta charset=\"utf-8\"><title>{title}</title><pre>{text}</pre>"
                )
        path = settings.snapshot_dir / f"{doc_id}.html"
        if not path.exists():
            return HTMLResponse("<h1>Snapshot not found</h1>", status_code=404)
        return HTMLResponse(path.read_text(encoding="utf-8", errors="ignore"))

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, session: str | None = Cookie(default=None)):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": current_user(storage, session), "message": ""},
        )

    @app.post("/login")
    def login(request: Request, username: str = Form(...), password: str = Form(...)):
        ok, message, token = auth.login(username, password)
        if not ok or token is None:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "user": None, "message": message},
                status_code=401,
            )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("session", token, httponly=True, samesite="lax")
        return response

    @app.get("/register", response_class=HTMLResponse)
    def register_form(request: Request, session: str | None = Cookie(default=None)):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "user": current_user(storage, session), "message": ""},
        )

    @app.post("/register")
    def register(request: Request, username: str = Form(...), password: str = Form(...), interests: str = Form(default="")):
        ok, message = auth.register(username, password, interests)
        if not ok:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "user": None, "message": message},
                status_code=400,
            )
        ok, _, token = auth.login(username, password)
        response = RedirectResponse("/", status_code=303)
        if ok and token:
            response.set_cookie("session", token, httponly=True, samesite="lax")
        return response

    @app.get("/logout")
    def logout(session: str | None = Cookie(default=None)):
        storage.delete_session(session)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("session")
        return response

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request, session: str | None = Cookie(default=None)):
        user = current_user(storage, session)
        rows = storage.query_history(user["id"] if user else None, limit=100)
        return templates.TemplateResponse(
            "history.html",
            {"request": request, "user": user, "rows": rows},
        )

    @app.get("/health")
    @app.get("/api/health")
    def health():
        return JSONResponse(backend_status(active_backend()))

    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def spa_fallback(full_path: str):
        if FRONTEND_INDEX.exists():
            return frontend_shell()
        return HTMLResponse("<h1>Not found</h1>", status_code=404)

    return app


app = create_app()



