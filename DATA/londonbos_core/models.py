"""Contratos de datos del dominio London-BOS.

Este módulo no conoce IB, SQLite, Telegram ni HTML. Sus dataclasses son el
contrato común entre adquisición de datos, reglas, persistencia y dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    NO_OPERABLE = "NO_OPERABLE"
    NO_BREAKOUT = "NO_BREAKOUT"
    ARMED = "ARMED"
    OPEN = "OPEN"
    BREAK_EVEN = "BREAK_EVEN"
    PARTIAL = "PARTIAL"
    TRAILING = "TRAILING"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class StrategyConfig:
    min_range_pips: float = 15.0
    max_range_pips: float = 40.0
    entry_buffer_pips: float = 2.0
    target_rr: float = 1.5
    partial_rr: Optional[float] = None
    partial_fraction: float = 0.5
    trailing_step_pips: float = 10.0
    close_hour_lima: int = 11

    def __post_init__(self) -> None:
        if self.min_range_pips < 0 or self.max_range_pips <= self.min_range_pips:
            raise ValueError("Los límites del rango deben ser positivos y ordenados")
        if self.entry_buffer_pips < 0 or self.target_rr <= 0:
            raise ValueError("El buffer y el RR deben ser positivos")
        if not 0 < self.partial_fraction <= 1:
            raise ValueError("partial_fraction debe estar entre 0 y 1")
        if self.partial_rr is not None and self.partial_rr <= self.target_rr:
            raise ValueError("partial_rr debe ser mayor que target_rr para permitir una salida parcial")


@dataclass(frozen=True)
class SessionBox:
    session_date: str
    start: datetime
    end: datetime
    high: float
    low: float
    bars: int
    source: str = "unknown"

    @property
    def range_pips(self) -> float:
        return (self.high - self.low) * 10000


@dataclass(frozen=True)
class TradePlan:
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    risk_price: float
    risk_pips: float
    target_rr: float


@dataclass(frozen=True)
class BreakoutSnapshot:
    price: float
    status: TradeStatus
    direction: Optional[Direction] = None
    r_multiple: Optional[float] = None
    message: str = ""


@dataclass(frozen=True)
class TradeEvent:
    event: str
    timestamp: datetime
    price: Optional[float] = None
    r_multiple: Optional[float] = None
    metadata: dict[str, object] = field(default_factory=dict)
