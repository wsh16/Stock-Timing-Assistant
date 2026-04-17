from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class WatchlistRule:
    id: int
    market: str
    symbol: str
    display_name: str
    benchmark_symbol: str
    benchmark_name: str
    monitor_mode: str
    window_days: int
    poll_interval_minutes: int
    cooldown_trading_days: int
    buy_benchmark_min_pct: float
    buy_stock_max_pct: float
    buy_divergence_min_pct: float
    sell_benchmark_max_pct: float
    sell_stock_min_pct: float
    sell_divergence_min_pct: float
    enabled: bool
    notes: str
    created_at: str
    updated_at: str
    last_checked_at: Optional[str] = None
    last_triggered_at: Optional[str] = None


@dataclass(slots=True)
class MarketSnapshot:
    market: str
    symbol: str
    name: str
    current_price: float
    previous_close: float
    timestamp: datetime
    source: str

    @property
    def daily_change_pct(self) -> float:
        if not self.previous_close:
            return 0.0
        return (self.current_price / self.previous_close - 1) * 100


@dataclass(slots=True)
class EvaluationResult:
    side: str
    monitor_mode: str
    stock_change_pct: float
    benchmark_change_pct: float
    divergence_pct: float
    explanation: str
