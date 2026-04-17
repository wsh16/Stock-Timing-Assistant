from __future__ import annotations

import re

from timing_assistant.constants import A_SHARE_BENCHMARKS, US_BENCHMARKS

A_BENCHMARK_NAME_MAP = {
    item["label"]: item["symbol"] for item in A_SHARE_BENCHMARKS
}
US_BENCHMARK_NAME_MAP = {
    item["label"]: item["symbol"] for item in US_BENCHMARKS
}


def normalize_market(value: str) -> str:
    market = (value or "").strip().upper()
    if market in {"A", "CN"}:
        return "A"
    if market in {"US", "USA"}:
        return "US"
    raise ValueError("仅支持 A股 或 美股")


def normalize_symbol(market: str, symbol: str, *, is_benchmark: bool = False) -> str:
    market = normalize_market(market)
    raw = (symbol or "").strip()
    if not raw:
        raise ValueError("代码不能为空")

    if market == "US":
        return raw.upper()

    aliases = A_BENCHMARK_NAME_MAP if is_benchmark else {}
    if raw in aliases:
        return aliases[raw]

    lowered = raw.lower().replace(" ", "")
    if lowered in A_BENCHMARK_NAME_MAP.values():
        return lowered

    match = re.fullmatch(r"(\d{6})(?:\.(sh|sz))?", lowered, re.IGNORECASE)
    if match:
        code, suffix = match.groups()
        if suffix:
            return f"{suffix.lower()}{code}"
        if code == "399006":
            return f"sz{code}"
        if code == "000300":
            return f"sh{code}"
        if code.startswith(("5", "6", "9")):
            return f"sh{code}"
        return f"sz{code}"

    if lowered.startswith(("sh", "sz")) and len(lowered) == 8:
        return lowered

    raise ValueError("A股代码格式不正确，例如 600519、000001.SZ、sh000001")


def symbol_without_prefix(symbol: str) -> str:
    cleaned = (symbol or "").strip().lower()
    if cleaned.startswith(("sh", "sz")):
        return cleaned[2:]
    return cleaned.replace(".sh", "").replace(".sz", "")


def get_default_benchmarks(market: str) -> list[dict[str, str]]:
    if normalize_market(market) == "A":
        return A_SHARE_BENCHMARKS
    return US_BENCHMARKS
