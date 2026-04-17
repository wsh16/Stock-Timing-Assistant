from __future__ import annotations

from pathlib import Path

APP_NAME = "择时助手"
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "timing_assistant.db"
STREAMLIT_PORT = 8501
STREAMLIT_URL = f"http://localhost:{STREAMLIT_PORT}"

DEFAULT_POLL_MINUTES = 15
DEFAULT_WINDOW_DAYS = 5
DEFAULT_COOLDOWN_DAYS = 1
SCAN_INTERVAL_SECONDS = 60

A_SHARE_BENCHMARKS = [
    {"label": "上证指数", "symbol": "sh000001"},
    {"label": "沪深300", "symbol": "sh000300"},
    {"label": "创业板指", "symbol": "sz399006"},
]

US_BENCHMARKS = [
    {"label": "SPY", "symbol": "SPY"},
    {"label": "QQQ", "symbol": "QQQ"},
    {"label": "DIA", "symbol": "DIA"},
]

SETTINGS_DEFAULTS = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "finnhub_api_key": "",
    "worker_status": "未启动",
    "worker_last_heartbeat": "",
    "worker_last_error": "",
    "worker_last_cycle_summary": "",
}

MODE_LABELS = {
    "intraday": "日内",
    "cross_day": "跨日",
}

MARKET_LABELS = {
    "A": "A股",
    "US": "美股",
}
