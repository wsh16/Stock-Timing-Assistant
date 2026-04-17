from __future__ import annotations

from timing_assistant.constants import MODE_LABELS
from timing_assistant.models import EvaluationResult, MarketSnapshot, WatchlistRule


def _format_pct(value: float) -> str:
    return f"{value:+.2f}%"


def evaluate_rule(
    rule: WatchlistRule,
    stock_snapshot: MarketSnapshot,
    benchmark_snapshot: MarketSnapshot,
    *,
    stock_window_change_pct: float | None = None,
    benchmark_window_change_pct: float | None = None,
) -> list[EvaluationResult]:
    if rule.monitor_mode == "intraday":
        stock_change = stock_snapshot.daily_change_pct
        benchmark_change = benchmark_snapshot.daily_change_pct
    else:
        if stock_window_change_pct is None or benchmark_window_change_pct is None:
            raise ValueError("跨日模式需要传入窗口涨跌幅")
        stock_change = stock_window_change_pct
        benchmark_change = benchmark_window_change_pct

    results: list[EvaluationResult] = []

    buy_divergence = benchmark_change - stock_change
    if (
        benchmark_change >= rule.buy_benchmark_min_pct
        and stock_change <= rule.buy_stock_max_pct
        and buy_divergence >= rule.buy_divergence_min_pct
    ):
        results.append(
            EvaluationResult(
                side="buy",
                monitor_mode=rule.monitor_mode,
                stock_change_pct=stock_change,
                benchmark_change_pct=benchmark_change,
                divergence_pct=buy_divergence,
                explanation=(
                    f"{MODE_LABELS[rule.monitor_mode]}买入条件触发："
                    f"基准 {_format_pct(benchmark_change)}，"
                    f"个股 {_format_pct(stock_change)}，"
                    f"背离 {_format_pct(buy_divergence)}。"
                ),
            )
        )

    sell_divergence = stock_change - benchmark_change
    if (
        benchmark_change <= rule.sell_benchmark_max_pct
        and stock_change >= rule.sell_stock_min_pct
        and sell_divergence >= rule.sell_divergence_min_pct
    ):
        results.append(
            EvaluationResult(
                side="sell",
                monitor_mode=rule.monitor_mode,
                stock_change_pct=stock_change,
                benchmark_change_pct=benchmark_change,
                divergence_pct=sell_divergence,
                explanation=(
                    f"{MODE_LABELS[rule.monitor_mode]}卖出条件触发："
                    f"基准 {_format_pct(benchmark_change)}，"
                    f"个股 {_format_pct(stock_change)}，"
                    f"背离 {_format_pct(sell_divergence)}。"
                ),
            )
        )

    return results
