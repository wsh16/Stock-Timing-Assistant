from __future__ import annotations

from datetime import datetime, timezone

from timing_assistant.models import MarketSnapshot, WatchlistRule
from timing_assistant.rule_engine import evaluate_rule


def make_rule(**overrides):
    payload = {
        "id": 1,
        "market": "A",
        "symbol": "sz000001",
        "display_name": "平安银行",
        "benchmark_symbol": "sh000001",
        "benchmark_name": "上证指数",
        "monitor_mode": "intraday",
        "window_days": 5,
        "poll_interval_minutes": 15,
        "cooldown_trading_days": 1,
        "buy_benchmark_min_pct": 1.0,
        "buy_stock_max_pct": -0.5,
        "buy_divergence_min_pct": 2.0,
        "sell_benchmark_max_pct": -1.0,
        "sell_stock_min_pct": 0.5,
        "sell_divergence_min_pct": 2.0,
        "enabled": True,
        "notes": "",
        "created_at": "2026-04-16T00:00:00+00:00",
        "updated_at": "2026-04-16T00:00:00+00:00",
    }
    payload.update(overrides)
    return WatchlistRule(**payload)


def make_snapshot(current_price: float, previous_close: float) -> MarketSnapshot:
    return MarketSnapshot(
        market="A",
        symbol="test",
        name="test",
        current_price=current_price,
        previous_close=previous_close,
        timestamp=datetime.now(timezone.utc),
        source="unit-test",
    )


def test_intraday_buy_signal():
    rule = make_rule()
    stock = make_snapshot(current_price=98, previous_close=100)
    benchmark = make_snapshot(current_price=102, previous_close=100)
    results = evaluate_rule(rule, stock, benchmark)
    assert [item.side for item in results] == ["buy"]


def test_intraday_sell_signal():
    rule = make_rule()
    stock = make_snapshot(current_price=103, previous_close=100)
    benchmark = make_snapshot(current_price=98, previous_close=100)
    results = evaluate_rule(rule, stock, benchmark)
    assert [item.side for item in results] == ["sell"]


def test_cross_day_signal_uses_window_changes():
    rule = make_rule(monitor_mode="cross_day")
    stock = make_snapshot(current_price=100, previous_close=100)
    benchmark = make_snapshot(current_price=100, previous_close=100)
    results = evaluate_rule(
        rule,
        stock,
        benchmark,
        stock_window_change_pct=-2.0,
        benchmark_window_change_pct=4.0,
    )
    assert [item.side for item in results] == ["buy"]
