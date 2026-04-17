from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from timing_assistant.config import get_db_path
from timing_assistant.constants import SETTINGS_DEFAULTS
from timing_assistant.models import WatchlistRule


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def initialize_database() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                display_name TEXT NOT NULL,
                benchmark_symbol TEXT NOT NULL,
                benchmark_name TEXT NOT NULL,
                monitor_mode TEXT NOT NULL DEFAULT 'intraday',
                window_days INTEGER NOT NULL DEFAULT 5,
                poll_interval_minutes INTEGER NOT NULL DEFAULT 15,
                cooldown_trading_days INTEGER NOT NULL DEFAULT 1,
                buy_benchmark_min_pct REAL NOT NULL DEFAULT 1.0,
                buy_stock_max_pct REAL NOT NULL DEFAULT -0.5,
                buy_divergence_min_pct REAL NOT NULL DEFAULT 2.0,
                sell_benchmark_max_pct REAL NOT NULL DEFAULT -1.0,
                sell_stock_min_pct REAL NOT NULL DEFAULT 0.5,
                sell_divergence_min_pct REAL NOT NULL DEFAULT 2.0,
                enabled INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT,
                last_triggered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                benchmark_symbol TEXT NOT NULL,
                alert_side TEXT NOT NULL,
                monitor_mode TEXT NOT NULL,
                stock_change_pct REAL NOT NULL,
                benchmark_change_pct REAL NOT NULL,
                divergence_pct REAL NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                sent_success INTEGER NOT NULL DEFAULT 0,
                sent_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (watchlist_id) REFERENCES watchlists(id)
            );

            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        now = utc_now_iso()
        for key, value in SETTINGS_DEFAULTS.items():
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, value, now),
            )
        conn.commit()


def get_settings() -> dict[str, str]:
    initialize_database()
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def update_settings(values: dict[str, str]) -> None:
    initialize_database()
    now = utc_now_iso()
    with get_connection() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
        conn.commit()


def row_to_watchlist(row: sqlite3.Row) -> WatchlistRule:
    return WatchlistRule(
        id=row["id"],
        market=row["market"],
        symbol=row["symbol"],
        display_name=row["display_name"],
        benchmark_symbol=row["benchmark_symbol"],
        benchmark_name=row["benchmark_name"],
        monitor_mode=row["monitor_mode"],
        window_days=row["window_days"],
        poll_interval_minutes=row["poll_interval_minutes"],
        cooldown_trading_days=row["cooldown_trading_days"],
        buy_benchmark_min_pct=row["buy_benchmark_min_pct"],
        buy_stock_max_pct=row["buy_stock_max_pct"],
        buy_divergence_min_pct=row["buy_divergence_min_pct"],
        sell_benchmark_max_pct=row["sell_benchmark_max_pct"],
        sell_stock_min_pct=row["sell_stock_min_pct"],
        sell_divergence_min_pct=row["sell_divergence_min_pct"],
        enabled=bool(row["enabled"]),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_checked_at=row["last_checked_at"],
        last_triggered_at=row["last_triggered_at"],
    )


def list_watchlists(*, enabled_only: bool = False) -> list[WatchlistRule]:
    initialize_database()
    query = "SELECT * FROM watchlists"
    params: tuple[Any, ...] = ()
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY updated_at DESC, id DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_watchlist(row) for row in rows]


def get_watchlist(rule_id: int) -> WatchlistRule | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM watchlists WHERE id = ?",
            (rule_id,),
        ).fetchone()
    return row_to_watchlist(row) if row else None


def save_watchlist(values: dict[str, Any], *, rule_id: int | None = None) -> int:
    initialize_database()
    now = utc_now_iso()
    columns = [
        "market",
        "symbol",
        "display_name",
        "benchmark_symbol",
        "benchmark_name",
        "monitor_mode",
        "window_days",
        "poll_interval_minutes",
        "cooldown_trading_days",
        "buy_benchmark_min_pct",
        "buy_stock_max_pct",
        "buy_divergence_min_pct",
        "sell_benchmark_max_pct",
        "sell_stock_min_pct",
        "sell_divergence_min_pct",
        "enabled",
        "notes",
    ]
    payload = {key: values[key] for key in columns}
    with get_connection() as conn:
        if rule_id is None:
            payload["created_at"] = now
            payload["updated_at"] = now
            sql = f"""
                INSERT INTO watchlists ({", ".join(payload.keys())})
                VALUES ({", ".join(["?"] * len(payload))})
            """
            cur = conn.execute(sql, tuple(payload.values()))
            conn.commit()
            return int(cur.lastrowid)

        assignments = ", ".join(f"{column} = ?" for column in payload)
        conn.execute(
            f"""
            UPDATE watchlists
            SET {assignments}, updated_at = ?
            WHERE id = ?
            """,
            (*payload.values(), now, rule_id),
        )
        conn.commit()
        return rule_id


def set_watchlist_enabled(rule_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE watchlists SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, utc_now_iso(), rule_id),
        )
        conn.commit()


def delete_watchlist(rule_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlists WHERE id = ?", (rule_id,))
        conn.commit()


def update_watchlist_runtime(
    rule_id: int,
    *,
    last_checked_at: str | None = None,
    last_triggered_at: str | None = None,
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    if last_checked_at is not None:
        updates.append("last_checked_at = ?")
        params.append(last_checked_at)
    if last_triggered_at is not None:
        updates.append("last_triggered_at = ?")
        params.append(last_triggered_at)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(utc_now_iso())
    params.append(rule_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE watchlists SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()


def get_recent_alert(rule_id: int, side: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM alert_logs
            WHERE watchlist_id = ? AND alert_side = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (rule_id, side),
        ).fetchone()
    return row


def log_alert(
    *,
    watchlist_id: int,
    symbol: str,
    benchmark_symbol: str,
    alert_side: str,
    monitor_mode: str,
    stock_change_pct: float,
    benchmark_change_pct: float,
    divergence_pct: float,
    message: str,
    payload: dict[str, Any],
    sent_success: bool,
    sent_error: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO alert_logs (
                watchlist_id, symbol, benchmark_symbol, alert_side, monitor_mode,
                stock_change_pct, benchmark_change_pct, divergence_pct,
                message, payload_json, sent_success, sent_error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watchlist_id,
                symbol,
                benchmark_symbol,
                alert_side,
                monitor_mode,
                stock_change_pct,
                benchmark_change_pct,
                divergence_pct,
                message,
                json.dumps(payload, ensure_ascii=False),
                1 if sent_success else 0,
                sent_error,
                utc_now_iso(),
            ),
        )
        conn.commit()


def list_alert_logs(limit: int | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        base_query = """
            SELECT
                a.*,
                w.display_name
            FROM alert_logs a
            LEFT JOIN watchlists w ON w.id = a.watchlist_id
            ORDER BY a.id DESC
        """
        if limit is None:
            rows = conn.execute(base_query).fetchall()
        else:
            rows = conn.execute(f"{base_query} LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def log_system_event(
    *,
    level: str,
    category: str,
    message: str,
    details: dict[str, Any] | str | None = None,
) -> None:
    payload: str
    if details is None:
        payload = "{}"
    elif isinstance(details, str):
        payload = json.dumps({"text": details}, ensure_ascii=False)
    else:
        payload = json.dumps(details, ensure_ascii=False)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_logs (level, category, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (level, category, message, payload, utc_now_iso()),
        )
        conn.commit()


def list_system_logs(limit: int | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        base_query = """
            SELECT id, level, category, message, details_json, created_at
            FROM system_logs
            ORDER BY id DESC
        """
        if limit is None:
            rows = conn.execute(base_query).fetchall()
        else:
            rows = conn.execute(f"{base_query} LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]
