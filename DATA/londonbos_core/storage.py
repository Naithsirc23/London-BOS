"""Persistencia local de eventos y migraciones ligeras de London-BOS."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1


def init_db(db_path: str | Path) -> None:
    """Crea las tablas necesarias sin borrar datos existentes."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS trade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_date TEXT,
                direction TEXT,
                price REAL,
                r_multiple REAL,
                source TEXT NOT NULL DEFAULT 'system',
                metadata TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_events_timestamp "
            "ON trade_events(timestamp DESC)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_events_session "
            "ON trade_events(session_date, timestamp DESC)"
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        con.execute(
            """INSERT INTO schema_meta(key, value) VALUES('version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (str(SCHEMA_VERSION),),
        )


def record_event(
    db_path: str | Path,
    event: str,
    *,
    timestamp: datetime | None = None,
    session_date: str | None = None,
    direction: str | None = None,
    price: float | None = None,
    r_multiple: float | None = None,
    source: str = "system",
    metadata: Mapping[str, Any] | None = None,
) -> int:
    """Registra un evento y devuelve su identificador."""
    if not event.strip():
        raise ValueError("event no puede estar vacío")
    init_db(db_path)
    occurred_at = timestamp or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    payload = json.dumps(dict(metadata or {}), ensure_ascii=False, default=str)
    with sqlite3.connect(db_path) as con:
        cursor = con.execute(
            """INSERT INTO trade_events
            (event, timestamp, session_date, direction, price, r_multiple, source, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event,
                occurred_at.isoformat(),
                session_date,
                direction,
                price,
                r_multiple,
                source,
                payload,
            ),
        )
        return int(cursor.lastrowid)


def decode_metadata(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    except json.JSONDecodeError:
        return {"raw": value}
