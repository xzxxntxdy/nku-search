from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import tempfile
from typing import Iterator

from .config import ensure_data_dirs, get_settings
from .models import utc_now_iso


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = Path(path or settings.sqlite_path)
        self.allow_fallback = path is None or self.path == settings.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.init_schema()
            self.assert_writable()
        except sqlite3.OperationalError:
            if not self.allow_fallback:
                raise
            self.path = Path(tempfile.gettempdir()) / "nku_search" / "search.db"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.init_schema()
            self.assert_writable()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    interests TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS query_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    site TEXT,
                    filetype TEXT,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS click_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    doc_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS suggestions (
                    term TEXT PRIMARY KEY,
                    weight REAL NOT NULL DEFAULT 1.0,
                    source TEXT NOT NULL DEFAULT 'index',
                    updated_at TEXT NOT NULL
                );
                """
            )

    def assert_writable(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_probe (
                    id INTEGER PRIMARY KEY,
                    touched_at TEXT NOT NULL
                )
                """
            )
            connection.execute("INSERT INTO storage_probe(touched_at) VALUES (?)", (utc_now_iso(),))
            connection.execute("DELETE FROM storage_probe")

    def create_user(self, username: str, password_hash: str, interests: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users(username, password_hash, interests, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, password_hash, interests, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    def get_user_by_id(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def update_user_interests(self, user_id: int, interests: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE users SET interests = ? WHERE id = ?",
                (interests.strip(), user_id),
            )

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, utc_now_iso()),
            )
        return token

    def get_user_by_session(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def log_query(
        self,
        query: str,
        mode: str,
        result_count: int,
        user_id: int | None = None,
        site: str | None = None,
        filetype: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO query_logs(user_id, query, mode, site, filetype, result_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, query, mode, site, filetype, result_count, utc_now_iso()),
            )

    def log_click(self, doc_id: str, url: str, title: str, user_id: int | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO click_logs(user_id, doc_id, url, title, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, doc_id, url, title, utc_now_iso()),
            )

    def query_history(self, user_id: int | None = None, limit: int = 50) -> list[sqlite3.Row]:
        sql = "SELECT * FROM query_logs"
        params: tuple[object, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params = (user_id,)
        sql += " ORDER BY id DESC LIMIT ?"
        params += (limit,)
        with self.connect() as connection:
            return list(connection.execute(sql, params).fetchall())

    def user_query_terms(self, user_id: int | None, limit: int = 30) -> list[str]:
        if user_id is None:
            return []
        terms: list[str] = []
        user = self.get_user_by_id(user_id)
        if user is not None and str(user["interests"]).strip():
            terms.append(str(user["interests"]).strip())
        terms.extend(row["query"] for row in self.query_history(user_id, limit))
        return terms[:limit]

    def upsert_suggestion(self, term: str, weight: float = 1.0, source: str = "index") -> None:
        term = term.strip()
        if not term:
            return
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO suggestions(term, weight, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(term) DO UPDATE SET
                    weight = suggestions.weight + excluded.weight,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (term, weight, source, utc_now_iso()),
            )

    def suggestions(self, prefix: str = "", limit: int = 10, user_id: int | None = None) -> list[str]:
        prefix = prefix.strip()
        terms: list[str] = []
        with self.connect() as connection:
            if user_id is not None:
                rows = connection.execute(
                    """
                    SELECT query AS term, COUNT(*) AS weight
                    FROM query_logs
                    WHERE user_id = ? AND query LIKE ?
                    GROUP BY query
                    ORDER BY weight DESC, MAX(id) DESC
                    LIMIT ?
                    """,
                    (user_id, f"{prefix}%", limit),
                ).fetchall()
                terms.extend(row["term"] for row in rows)
            rows = connection.execute(
                """
                SELECT term
                FROM suggestions
                WHERE term LIKE ?
                ORDER BY weight DESC, updated_at DESC
                LIMIT ?
                """,
                (f"{prefix}%", limit),
            ).fetchall()
            for row in rows:
                if row["term"] not in terms:
                    terms.append(row["term"])
        return terms[:limit]

