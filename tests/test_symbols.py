from __future__ import annotations

from timing_assistant.symbols import normalize_symbol


def test_normalize_a_share_stock():
    assert normalize_symbol("A", "000001.SZ") == "sz000001"
    assert normalize_symbol("A", "600519") == "sh600519"


def test_normalize_a_share_benchmark():
    assert normalize_symbol("A", "上证指数", is_benchmark=True) == "sh000001"
    assert normalize_symbol("A", "000300", is_benchmark=True) == "sh000300"


def test_normalize_us_symbol():
    assert normalize_symbol("US", "aapl") == "AAPL"
