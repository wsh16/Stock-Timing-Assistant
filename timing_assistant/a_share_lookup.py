from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import requests

from timing_assistant.symbols import normalize_symbol

SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0",
}


@dataclass(frozen=True, slots=True)
class AShareMatch:
    raw_input: str
    normalized_symbol: str
    display_name: str


@lru_cache(maxsize=512)
def lookup_a_share_match(raw_symbol: str) -> AShareMatch | None:
    raw = (raw_symbol or "").strip()
    if not raw:
        return None

    try:
        normalized_symbol = normalize_symbol("A", raw)
    except ValueError:
        return None

    try:
        response = requests.get(
            SINA_QUOTE_URL + normalized_symbol,
            headers=SINA_HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        match = re.search(rf'var hq_str_{normalized_symbol}="(?P<data>.*)";', response.text)
        if not match:
            return AShareMatch(raw, normalized_symbol, "")
        fields = match.group("data").split(",")
        name = fields[0].strip() if fields else ""
        return AShareMatch(raw, normalized_symbol, name)
    except Exception:  # noqa: BLE001
        return AShareMatch(raw, normalized_symbol, "")
