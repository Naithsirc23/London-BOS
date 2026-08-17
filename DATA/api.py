"""API de lectura para el dashboard modular London-BOS.

Arranque local:
    PYTHONPATH=DATA uvicorn api:app --app-dir DATA --host 127.0.0.1 --port 8080

Esta API es deliberadamente read-only: no coloca órdenes ni envía notificaciones.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from londonbos_core.storage import decode_metadata, init_db

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("LONDONBOS_DB", BASE_DIR / "londonbos_log.db"))

app = FastAPI(title="London-BOS", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept"],
)


def _ensure_db() -> None:
    init_db(DB_PATH)


def _query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    _ensure_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def _tables() -> list[str]:
    _ensure_db()
    with sqlite3.connect(DB_PATH) as con:
        return [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]


def _latest_timestamp(rows: list[dict[str, Any]], key: str) -> str | None:
    return rows[0].get(key) if rows else None


@app.get("/api/health")
def health() -> dict[str, Any]:
    _ensure_db()
    return {
        "status": "ok",
        "service": "london-bos-api",
        "mode": "read_only",
        "database": str(DB_PATH),
        "database_exists": DB_PATH.exists(),
        "tables": _tables(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/session/latest")
def latest_session() -> dict[str, Any]:
    rows = _query(
        "SELECT fecha, maximo, minimo, rango_pips, operable, barras, generado, "
        "ruptura_20, ruptura_60 FROM sesiones ORDER BY fecha DESC LIMIT 1"
    ) if "sesiones" in _tables() else []
    return {
        "data": rows[0] if rows else None,
        "freshness": {
            "updated_at": rows[0].get("generado") if rows else None,
            "source": "sqlite",
        },
    }


@app.get("/api/session/history")
def session_history(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    rows = _query(
        "SELECT fecha, maximo, minimo, rango_pips, operable, barras, generado, "
        "ruptura_20, ruptura_60 FROM sesiones ORDER BY fecha DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) if "sesiones" in _tables() else []
    return {
        "data": rows,
        "limit": limit,
        "offset": offset,
        "freshness": {"updated_at": _latest_timestamp(rows, "generado"), "source": "sqlite"},
    }


@app.get("/api/paper-trades")
def paper_trades(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    rows = _query(
        "SELECT fecha, direccion, entry, sl, tp, salida, r FROM paper "
        "ORDER BY fecha DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) if "paper" in _tables() else []
    return {"data": rows, "limit": limit, "offset": offset, "freshness": {"source": "sqlite"}}


@app.get("/api/events")
def events(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    rows = _query(
        "SELECT id, event, timestamp, session_date, direction, price, r_multiple, "
        "source, metadata FROM trade_events ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    for row in rows:
        row["metadata"] = decode_metadata(row.get("metadata"))
    return {
        "data": rows,
        "available": True,
        "limit": limit,
        "offset": offset,
        "freshness": {
            "updated_at": _latest_timestamp(rows, "timestamp"),
            "source": "sqlite",
        },
    }
