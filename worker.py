from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from timing_assistant.constants import (
    APP_NAME,
    MARKET_LABELS,
    MODE_LABELS,
    SCAN_INTERVAL_SECONDS,
)
from timing_assistant.database import (
    get_recent_alert,
    get_settings,
    initialize_database,
    list_watchlists,
    log_alert,
    log_system_event,
    update_settings,
    update_watchlist_runtime,
)
from timing_assistant.market_data import MarketDataService
from timing_assistant.market_hours import (
    current_market_time,
    is_market_open,
    trading_day_distance,
)
from timing_assistant.models import EvaluationResult, MarketSnapshot, WatchlistRule
from timing_assistant.notifier import TelegramNotifier
from timing_assistant.rule_engine import evaluate_rule


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger(APP_NAME)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_check_rule(rule: WatchlistRule, now: datetime) -> bool:
    last_checked = parse_iso(rule.last_checked_at)
    if last_checked is None:
        return True
    return now - last_checked >= timedelta(minutes=rule.poll_interval_minutes)


def in_cooldown(rule: WatchlistRule, side: str, now: datetime) -> bool:
    if rule.cooldown_trading_days <= 0:
        return False

    recent = get_recent_alert(rule.id, side)
    if recent is None:
        return False

    last_sent = parse_iso(recent["created_at"])
    if last_sent is None:
        return False

    start_day = current_market_time(rule.market, last_sent).date()
    end_day = current_market_time(rule.market, now).date()
    return trading_day_distance(rule.market, start_day, end_day) < rule.cooldown_trading_days


def format_alert_message(
    rule: WatchlistRule,
    result: EvaluationResult,
    stock: MarketSnapshot,
    benchmark: MarketSnapshot,
) -> str:
    side_label = "买入提醒" if result.side == "buy" else "卖出提醒"
    mode_label = MODE_LABELS[result.monitor_mode]
    return "\n".join(
        [
            f"{side_label} | {mode_label} | {MARKET_LABELS[rule.market]}",
            f"股票: {rule.display_name} ({rule.symbol.upper()})",
            f"基准: {rule.benchmark_name} ({rule.benchmark_symbol.upper()})",
            f"现价: {stock.current_price:.2f}",
            f"个股变化: {result.stock_change_pct:+.2f}%",
            f"基准变化: {result.benchmark_change_pct:+.2f}%",
            f"背离值: {result.divergence_pct:+.2f}%",
            f"触发时间: {stock.timestamp.astimezone(timezone.utc).isoformat()}",
            result.explanation,
        ]
    )


def process_rule(
    rule: WatchlistRule,
    *,
    now: datetime,
    market_data: MarketDataService,
    notifier: TelegramNotifier,
) -> dict[str, int]:
    counters = {"checked": 0, "alerts": 0, "sent": 0, "send_failed": 0, "cooldown": 0}
    snapshots = market_data.get_snapshots(rule.market, [rule.symbol, rule.benchmark_symbol])
    stock = snapshots.get(rule.symbol)
    benchmark = snapshots.get(rule.benchmark_symbol)
    if stock is None or benchmark is None:
        raise RuntimeError("行情快照不完整")

    eval_kwargs: dict[str, float] = {}
    if rule.monitor_mode == "cross_day":
        eval_kwargs["stock_window_change_pct"] = market_data.get_window_change_pct(
            rule.market,
            rule.symbol,
            current_price=stock.current_price,
            window_days=rule.window_days,
            is_benchmark=False,
        )
        eval_kwargs["benchmark_window_change_pct"] = market_data.get_window_change_pct(
            rule.market,
            rule.benchmark_symbol,
            current_price=benchmark.current_price,
            window_days=rule.window_days,
            is_benchmark=True,
        )

    results = evaluate_rule(rule, stock, benchmark, **eval_kwargs)
    counters["checked"] += 1
    update_watchlist_runtime(rule.id, last_checked_at=now.isoformat())

    for result in results:
        if in_cooldown(rule, result.side, now):
            counters["cooldown"] += 1
            continue

        message = format_alert_message(rule, result, stock, benchmark)
        notification = notifier.send_message(message)
        payload = {
            "stock_name": stock.name,
            "benchmark_name": benchmark.name,
            "stock_price": stock.current_price,
            "benchmark_price": benchmark.current_price,
            "timestamp": stock.timestamp.isoformat(),
            "explanation": result.explanation,
        }
        log_alert(
            watchlist_id=rule.id,
            symbol=rule.symbol,
            benchmark_symbol=rule.benchmark_symbol,
            alert_side=result.side,
            monitor_mode=result.monitor_mode,
            stock_change_pct=result.stock_change_pct,
            benchmark_change_pct=result.benchmark_change_pct,
            divergence_pct=result.divergence_pct,
            message=message,
            payload=payload,
            sent_success=notification.success,
            sent_error=notification.error,
        )
        update_watchlist_runtime(rule.id, last_triggered_at=now.isoformat())
        counters["alerts"] += 1
        if notification.success:
            counters["sent"] += 1
        else:
            counters["send_failed"] += 1

    return counters


def run_cycle() -> None:
    initialize_database()
    now = datetime.now(timezone.utc)
    settings = get_settings()
    previous_summary = settings.get("worker_last_cycle_summary", "")
    market_data = MarketDataService(settings.get("finnhub_api_key", ""))
    notifier = TelegramNotifier(
        settings.get("telegram_bot_token", ""),
        settings.get("telegram_chat_id", ""),
    )

    counters = {
        "due": 0,
        "checked": 0,
        "alerts": 0,
        "sent": 0,
        "send_failed": 0,
        "market_closed": 0,
        "cooldown": 0,
        "errors": 0,
    }
    errors: list[str] = []

    for rule in list_watchlists(enabled_only=True):
        if not is_market_open(rule.market, now):
            counters["market_closed"] += 1
            continue

        if not should_check_rule(rule, now):
            continue
        counters["due"] += 1

        try:
            result = process_rule(
                rule,
                now=now,
                market_data=market_data,
                notifier=notifier,
            )
            for key, value in result.items():
                counters[key] += value
        except Exception as exc:  # noqa: BLE001
            counters["errors"] += 1
            error_message = f"{rule.display_name}({rule.symbol}): {exc}"
            errors.append(error_message)
            update_watchlist_runtime(rule.id, last_checked_at=now.isoformat())
            LOGGER.exception("规则处理失败: %s", rule.symbol)
            log_system_event(
                level="ERROR",
                category="worker.rule",
                message=f"规则处理失败: {rule.display_name} ({rule.symbol})",
                details={
                    "rule_id": rule.id,
                    "symbol": rule.symbol,
                    "benchmark_symbol": rule.benchmark_symbol,
                    "monitor_mode": rule.monitor_mode,
                    "error": str(exc),
                },
            )

    summary = (
        f"本轮扫描: 到期 {counters['due']} 条, "
        f"检查 {counters['checked']} 条, "
        f"触发 {counters['alerts']} 条, "
        f"发送成功 {counters['sent']} 条, "
        f"市场关闭跳过 {counters['market_closed']} 条, "
        f"冷却跳过 {counters['cooldown']} 条, "
        f"错误 {counters['errors']} 条"
    )

    should_log_cycle = (
        counters["due"] > 0
        or counters["checked"] > 0
        or counters["alerts"] > 0
        or counters["send_failed"] > 0
        or counters["errors"] > 0
    )
    settings_payload = {
        "worker_status": "运行中",
        "worker_last_heartbeat": now.isoformat(),
        "worker_last_error": " | ".join(errors[:3]),
    }
    if should_log_cycle or not previous_summary:
        settings_payload["worker_last_cycle_summary"] = summary
    update_settings(settings_payload)
    if should_log_cycle:
        log_system_event(
            level="INFO" if counters["errors"] == 0 else "WARNING",
            category="worker.cycle",
            message=summary,
            details={
                **counters,
                "errors": errors,
                "timestamp": now.isoformat(),
            },
        )
    LOGGER.info(summary)


def main() -> None:
    initialize_database()
    update_settings({"worker_status": "启动中"})
    log_system_event(
        level="INFO",
        category="worker.lifecycle",
        message="后台监控启动",
        details={"status": "starting"},
    )
    run_cycle()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_cycle,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="scan-watchlists",
        max_instances=1,
        coalesce=True,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        update_settings({"worker_status": "已停止"})
        log_system_event(
            level="INFO",
            category="worker.lifecycle",
            message="后台监控停止",
            details={"status": "stopped"},
        )
        LOGGER.info("后台监控已停止")


if __name__ == "__main__":
    main()
