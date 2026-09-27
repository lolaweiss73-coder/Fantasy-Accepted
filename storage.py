from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FANTASY_DATA_DIR", str(BASE_DIR))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_PATH = DATA_DIR / "fantasy_accepted.db"

if USE_POSTGRES and psycopg is None:
    raise RuntimeError("DATABASE_URL is set but psycopg is not installed")


class Connection:
    def __init__(self, raw: Any, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgres else sql

    def execute(self, sql: str, params: Any = ()):
        return self.raw.execute(self._sql(sql), params)

    def executescript(self, script: str) -> None:
        if not self.postgres:
            self.raw.executescript(script)
            return
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.raw.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def db() -> Connection:
    if USE_POSTGRES:
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        return Connection(raw, True)
    raw = sqlite3.connect(SQLITE_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    return Connection(raw, False)


INTEGRITY_ERRORS = (psycopg.IntegrityError,) if USE_POSTGRES else (sqlite3.IntegrityError,)


def backend_name() -> str:
    return "postgres" if USE_POSTGRES else "sqlite"
