from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import akshare as ak
import pandas as pd
import requests

from timing_assistant.market_hours import current_market_time, get_market_timezone
from timing_assistant.models import MarketSnapshot
from timing_assistant.symbols import symbol_without_prefix


SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0",
}


@dataclass(slots=True)
class HistoricalSeries:
    symbol: str
    dates: list[datetime]
    closes: list[float]

    def base_close_for_window(self, window_days: int) -> float:
        if len(self.closes) <= window_days:
            raise ValueError("历史数据不足，无法计算跨日背离")
        return self.closes[-(window_days + 1)]


class MarketDataService:
    def __init__(self, finnhub_api_key: str = "") -> None:
        self.finnhub_api_key = (finnhub_api_key or "").strip()
        self.session = requests.Session()
        self._history_cache: dict[tuple[str, str], HistoricalSeries] = {}

    def get_snapshots(self, market: str, symbols: Iterable[str]) -> dict[str, MarketSnapshot]:
        if market == "A":
            return self._fetch_cn_snapshots(symbols)
        return self._fetch_us_snapshots(symbols)

    def get_window_change_pct(
        self,
        market: str,
        symbol: str,
        *,
        current_price: float,
        window_days: int,
        is_benchmark: bool = False,
    ) -> float:
        history = self.get_daily_history(market, symbol, is_benchmark=is_benchmark)
        base_close = history.base_close_for_window(window_days)
        if math.isclose(base_close, 0.0):
            return 0.0
        return (current_price / base_close - 1) * 100

    def get_daily_history(
        self,
        market: str,
        symbol: str,
        *,
        is_benchmark: bool = False,
    ) -> HistoricalSeries:
        cache_key = (market, symbol, "benchmark" if is_benchmark else "stock")
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        if market == "A":
            history = self._fetch_cn_daily_history(symbol, is_benchmark=is_benchmark)
        else:
            history = self._fetch_us_daily_history(symbol)
        self._history_cache[cache_key] = history
        return history

    def clear_cache(self) -> None:
        self._history_cache.clear()

    def _fetch_cn_snapshots(self, symbols: Iterable[str]) -> dict[str, MarketSnapshot]:
        normalized = [symbol.strip().lower() for symbol in symbols]
        response = self.session.get(
            SINA_QUOTE_URL + ",".join(normalized),
            headers=SINA_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        snapshots: dict[str, MarketSnapshot] = {}
        for line in response.text.strip().splitlines():
            match = re.match(r'var hq_str_(?P<symbol>[^=]+)="(?P<data>.*)";', line)
            if not match:
                continue
            symbol = match.group("symbol").lower()
            data = match.group("data")
            fields = data.split(",")
            if len(fields) < 32:
                continue
            name = fields[0] or symbol.upper()
            open_price = _safe_float(fields[1])
            previous_close = _safe_float(fields[2])
            current_price = _safe_float(fields[3]) or open_price
            date_part = fields[30] or current_market_time("A").date().isoformat()
            time_part = fields[31] or "15:00:00"
            timestamp = datetime.fromisoformat(f"{date_part}T{time_part}").replace(
                tzinfo=get_market_timezone("A")
            ).astimezone(timezone.utc)
            snapshots[symbol] = MarketSnapshot(
                market="A",
                symbol=symbol,
                name=name,
                current_price=current_price,
                previous_close=previous_close,
                timestamp=timestamp,
                source="sina",
            )
        return snapshots

    def _fetch_us_snapshots(self, symbols: Iterable[str]) -> dict[str, MarketSnapshot]:
        if not self.finnhub_api_key:
            raise RuntimeError("缺少 Finnhub API Key，无法获取美股行情")

        snapshots: dict[str, MarketSnapshot] = {}
        for symbol in symbols:
            upper_symbol = symbol.strip().upper()
            response = self.session.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": upper_symbol, "token": self.finnhub_api_key},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            current_price = _safe_float(payload.get("c"))
            previous_close = _safe_float(payload.get("pc"))
            timestamp = datetime.fromtimestamp(
                int(payload.get("t") or datetime.now().timestamp()),
                tz=timezone.utc,
            )
            snapshots[upper_symbol] = MarketSnapshot(
                market="US",
                symbol=upper_symbol,
                name=upper_symbol,
                current_price=current_price,
                previous_close=previous_close,
                timestamp=timestamp,
                source="finnhub",
            )
        return snapshots

    def _fetch_cn_daily_history(self, symbol: str, *, is_benchmark: bool) -> HistoricalSeries:
        if is_benchmark:
            series = self._fetch_cn_index_history(symbol)
        else:
            series = self._fetch_cn_stock_history(symbol)
        return series

    def _fetch_cn_stock_history(self, symbol: str) -> HistoricalSeries:
        code = symbol_without_prefix(symbol)
        start_date = (current_market_time("A") - timedelta(days=120)).strftime("%Y%m%d")
        end_date = current_market_time("A").strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="",
        )
        dates = [datetime.fromisoformat(str(item)) for item in df["日期"].tolist()]
        closes = [float(item) for item in df["收盘"].tolist()]
        return HistoricalSeries(symbol=symbol, dates=dates, closes=closes)

    def _fetch_cn_index_history(self, symbol: str) -> HistoricalSeries:
        errors: list[str] = []
        for fetcher in (ak.stock_zh_index_daily, ak.stock_zh_index_daily_tx):
            try:
                df = fetcher(symbol=symbol)
                if df.empty:
                    continue
                date_col = "date"
                close_col = "close"
                dates = [pd.Timestamp(item).to_pydatetime() for item in df[date_col].tolist()]
                closes = [float(item) for item in df[close_col].tolist()]
                return HistoricalSeries(symbol=symbol, dates=dates, closes=closes)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        raise RuntimeError(f"A股指数历史数据获取失败: {' | '.join(errors)}")

    def _fetch_us_daily_history(self, symbol: str) -> HistoricalSeries:
        if not self.finnhub_api_key:
            raise RuntimeError("缺少 Finnhub API Key，无法获取美股历史数据")

        end_time = int(datetime.now(tz=timezone.utc).timestamp())
        start_time = int((datetime.now(tz=timezone.utc) - timedelta(days=180)).timestamp())
        response = self.session.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol": symbol.upper(),
                "resolution": "D",
                "from": start_time,
                "to": end_time,
                "token": self.finnhub_api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("s") != "ok":
            raise RuntimeError(f"Finnhub 历史数据返回异常: {payload}")
        dates = [
            datetime.fromtimestamp(int(item), tz=timezone.utc)
            for item in payload.get("t", [])
        ]
        closes = [float(item) for item in payload.get("c", [])]
        return HistoricalSeries(symbol=symbol.upper(), dates=dates, closes=closes)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
