from datetime import datetime, timezone

import pytest

from londonbos_core.models import Direction, SessionBox, StrategyConfig, TradeStatus
from londonbos_core.rules import (
    build_plan,
    evaluate_breakout,
    is_operable,
    management_thresholds,
)


@pytest.fixture
def box():
    return SessionBox(
        session_date="2026-08-17",
        start=datetime(2026, 8, 16, 19, tzinfo=timezone.utc),
        end=datetime(2026, 8, 17, 2, tzinfo=timezone.utc),
        high=1.1050,
        low=1.1030,
        bars=420,
        source="test",
    )


def test_operable_range_and_plan(box):
    config = StrategyConfig()
    assert box.range_pips == pytest.approx(20.0)
    assert is_operable(box, config)

    buy = build_plan(box, Direction.BUY, config)
    sell = build_plan(box, Direction.SELL, config)
    assert buy.entry == pytest.approx(1.1052)
    assert sell.entry == pytest.approx(1.1028)
    assert buy.risk_pips == pytest.approx(22.0)
    assert buy.take_profit > buy.entry
    assert sell.take_profit < sell.entry


def test_breakout_states(box):
    config = StrategyConfig()
    inside = evaluate_breakout(1.1040, box, config)
    assert inside.status is TradeStatus.NO_BREAKOUT

    buy = build_plan(box, Direction.BUY, config)
    open_buy = evaluate_breakout(buy.entry + buy.risk_price * 0.5, box, config)
    assert open_buy.status is TradeStatus.OPEN
    assert open_buy.direction is Direction.BUY
    assert open_buy.r_multiple == pytest.approx(0.5)

    tp_buy = evaluate_breakout(buy.take_profit, box, config)
    assert tp_buy.status is TradeStatus.CLOSED
    assert tp_buy.r_multiple == pytest.approx(1.5)


def test_partial_is_disabled_when_tp_is_1_5r(box):
    plan = build_plan(box, Direction.BUY, StrategyConfig())
    thresholds = management_thresholds(plan, StrategyConfig())
    assert thresholds["break_even"] is not None
    assert thresholds["partial"] is None


def test_partial_can_be_enabled_above_target(box):
    config = StrategyConfig(target_rr=1.5, partial_rr=2.0)
    plan = build_plan(box, Direction.BUY, config)
    thresholds = management_thresholds(plan, config)
    assert thresholds["partial"] == pytest.approx(plan.entry + 2 * plan.risk_price)


def test_non_operable_box_is_not_tradable(box):
    narrow = SessionBox(
        session_date=box.session_date,
        start=box.start,
        end=box.end,
        high=1.1040,
        low=1.1038,
        bars=420,
        source="test",
    )
    assert not is_operable(narrow, StrategyConfig())
    with pytest.raises(ValueError):
        build_plan(narrow, Direction.BUY)
