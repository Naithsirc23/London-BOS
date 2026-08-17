"""Reglas puras de London-BOS.

Todas las funciones son deterministas y no producen efectos secundarios, lo que
permite reutilizarlas desde paper trading, API, dashboard y tests.
"""
from __future__ import annotations

from .models import (
    BreakoutSnapshot,
    Direction,
    SessionBox,
    StrategyConfig,
    TradePlan,
    TradeStatus,
)


def is_operable(box: SessionBox, config: StrategyConfig) -> bool:
    return config.min_range_pips <= box.range_pips <= config.max_range_pips


def build_plan(
    box: SessionBox,
    direction: Direction,
    config: StrategyConfig = StrategyConfig(),
) -> TradePlan:
    if not is_operable(box, config):
        raise ValueError("No se puede construir un plan para un box no operable")

    buffer = config.entry_buffer_pips / 10000
    if direction is Direction.BUY:
        entry = box.high + buffer
        stop = box.low
        take_profit = entry + config.target_rr * (entry - stop)
    else:
        entry = box.low - buffer
        stop = box.high
        take_profit = entry - config.target_rr * (stop - entry)

    risk_price = abs(entry - stop)
    return TradePlan(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=take_profit,
        risk_price=risk_price,
        risk_pips=risk_price * 10000,
        target_rr=config.target_rr,
    )


def evaluate_breakout(
    price: float,
    box: SessionBox,
    config: StrategyConfig = StrategyConfig(),
) -> BreakoutSnapshot:
    if not is_operable(box, config):
        return BreakoutSnapshot(
            price=price,
            status=TradeStatus.NO_OPERABLE,
            message="El rango está fuera de la ventana operable.",
        )

    buy = build_plan(box, Direction.BUY, config)
    sell = build_plan(box, Direction.SELL, config)

    if price >= buy.entry:
        r = (price - buy.entry) / buy.risk_price
        if price >= buy.take_profit:
            status = TradeStatus.CLOSED
            message = "TP alcanzado en BUY."
        elif price <= buy.stop_loss:
            status = TradeStatus.CLOSED
            r = -1.0
            message = "SL alcanzado en BUY."
        else:
            status = TradeStatus.OPEN
            message = "BUY abierta."
        return BreakoutSnapshot(price, status, Direction.BUY, r, message)

    if price <= sell.entry:
        r = (sell.entry - price) / sell.risk_price
        if price <= sell.take_profit:
            status = TradeStatus.CLOSED
            message = "TP alcanzado en SELL."
        elif price >= sell.stop_loss:
            status = TradeStatus.CLOSED
            r = -1.0
            message = "SL alcanzado en SELL."
        else:
            status = TradeStatus.OPEN
            message = "SELL abierta."
        return BreakoutSnapshot(price, status, Direction.SELL, r, message)

    return BreakoutSnapshot(
        price=price,
        status=TradeStatus.NO_BREAKOUT,
        message="El precio sigue dentro del box.",
    )


def management_thresholds(
    plan: TradePlan,
    config: StrategyConfig = StrategyConfig(),
) -> dict[str, float | None]:
    """Devuelve umbrales de gestión coherentes con el TP configurado.

    La salida parcial solo se habilita si se configura un nivel superior al TP;
    por defecto queda desactivada porque el proyecto usa TP de 1.5R.
    """
    if plan.direction is Direction.BUY:
        be = plan.entry + plan.risk_price
        partial = (
            plan.entry + config.partial_rr * plan.risk_price
            if config.partial_rr is not None
            else None
        )
    else:
        be = plan.entry - plan.risk_price
        partial = (
            plan.entry - config.partial_rr * plan.risk_price
            if config.partial_rr is not None
            else None
        )
    return {"break_even": be, "partial": partial}
