"""Database connection layer.

Two backends:
  - "mysql"  : PyMySQL against the real MariaDB server (production path).
  - "sqlite" : stdlib sqlite3 against a restored copy of the dump. Used for
               local testing / read-only analysis. Tests never need production
               credentials.

SQL in the repository layer is deliberately portable (plain ANSI INSERT/UPDATE/
SELECT/DELETE with %s placeholders); the wrapper rewrites placeholders for
sqlite. No MySQL-specific constructs (ON DUPLICATE KEY, LAST_INSERT_ID()) are
used — generated ids are read from cursor.lastrowid, which both drivers support.

Safety model:
  - the connection runs in autocommit mode; each product import opens exactly
    one explicit transaction (BEGIN ... COMMIT / ROLLBACK) — see
    ProductImporter.execute().
  - `read_only=True` (dry-run) forbids every write statement at the wrapper
    level AND, for MariaDB, additionally sets the session read-only server-side.
"""
from __future__ import annotations

import re
from typing import Any

_WRITE_RE = re.compile(
    r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|TRUNCATE|RENAME|"
    r"LOAD|CALL|DO|SET|GRANT|REVOKE|HANDLER|LOCK|BEGIN|START)\b", re.IGNORECASE,
)


class ReadOnlyViolation(Exception):
    pass


class Database:
    """Thin wrapper providing dict rows, placeholder translation and tx control."""

    def __init__(self, connection: Any, backend: str) -> None:
        self.conn = connection
        self.backend = backend
        self._placeholder = "?" if backend == "sqlite" else "%s"
        #: set True for dry-run: every write statement raises ReadOnlyViolation
        self.read_only = False

    # -- construction ---------------------------------------------------------

    @classmethod
    def connect_mysql(
        cls, host: str, port: int, user: str, password: str, database: str,
        read_only: bool = False,
    ) -> Database:
        import pymysql  # imported lazily so pure-logic tests need no driver

        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            # autocommit: reads (plan/diff) are auto-committed and never hold an
            # implicit transaction open; the per-product import transaction is
            # opened explicitly with BEGIN.
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        db = cls(conn, "mysql")
        if read_only:
            # Belt: app-level guard. Braces: enforce at the server so even a
            # future code mistake cannot write during a dry-run.
            with conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            db.read_only = True
        return db

    @classmethod
    def connect_sqlite(cls, path: str, read_only: bool = False) -> Database:
        import sqlite3
        from pathlib import Path

        if read_only:
            uri = f"{Path(path).absolute().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        else:
            conn = sqlite3.connect(path, isolation_level=None)  # manual transactions
        conn.row_factory = sqlite3.Row
        db = cls(conn, "sqlite")
        db.read_only = read_only
        return db

    # -- execution -------------------------------------------------------------

    def _sql(self, sql: str) -> str:
        if self.backend == "sqlite":
            # No literal % exists in our SQL (percent signs only ever appear
            # inside bound parameters), so a plain replace is safe.
            return sql.replace("%s", self._placeholder)
        return sql

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        if self.read_only and _WRITE_RE.match(sql):
            raise ReadOnlyViolation(
                f"write statement attempted while connection is READ ONLY: "
                f"{sql.splitlines()[0][:80]}"
            )
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def query_all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        if self.backend == "sqlite":
            return [dict(r) for r in rows]
        return list(rows)

    def query_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row) if self.backend == "sqlite" else row

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        row = self.query_one(sql, params)
        if not row:
            return None
        return next(iter(row.values()))

    # -- transactions ------------------------------------------------------------
    # One transaction per product: BEGIN ... COMMIT, ROLLBACK on any failure.
    # The connection is in autocommit mode, so plan-phase reads never hold a
    # transaction open across products.

    def begin(self) -> None:
        if self.read_only:
            raise ReadOnlyViolation("cannot BEGIN a transaction in READ ONLY mode")
        if self.backend == "mysql":
            self.conn.begin()
        else:
            self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
