"""API de lectura para el dashboard modular London-BOS.

Arranque local:
    PYTHONPATH=DATA uvicorn api:app --app-dir DATA --host 127.0.0.1 --port 8080

La primera iteración es deliberadamente read-only: no coloca órdenes ni envía
notificaciones. La capa de dominio queda separada de esta interfaz.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("LONDONBOS_DB", BASE_DIR / "londonbos_log.db"))

app = FastAPI(title="London-BOS API", version="0.1.0")


def _query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def _tables() -> list[str]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as con:
        return [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "london-bos-api",
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
    )
    return {"data": rows[0] if rows else None}


@app.get("/api/session/history")
def session_history(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    rows = _query(
        "SELECT fecha, maximo, minimo, rango_pips, operable, barras, generado, "
        "ruptura_20, ruptura_60 FROM sesiones ORDER BY fecha DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {"data": rows, "limit": limit, "offset": offset}


@app.get("/api/paper-trades")
def paper_trades(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    rows = _query(
        "SELECT fecha, direccion, entry, sl, tp, salida, r FROM paper "
        "ORDER BY fecha DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {"data": rows, "limit": limit, "offset": offset}


@app.get("/api/events")
def events(limit: int = 50) -> dict[str, Any]:
    """Punto de extensión para la futura tabla trade_events."""
    limit = min(max(limit, 1), 200)
    if "trade_events" not in _tables():
        return {"data": [], "available": False, "limit": limit}
    rows = _query(
        "SELECT id, event, timestamp, price, r_multiple, metadata "
        "FROM trade_events ORDER BY timestamp DESC LIMIT ?", (limit,)
    )
    return {"data": rows, "available": True, "limit": limit}
