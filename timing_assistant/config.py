from __future__ import annotations

from pathlib import Path

from timing_assistant.constants import DATA_DIR, DB_PATH


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db_path() -> Path:
    ensure_runtime_dirs()
    return DB_PATH
