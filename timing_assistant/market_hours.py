from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

CALENDARS = {
    "A": xcals.get_calendar("XSHG"),
    "US": xcals.get_calendar("XNYS"),
}

TIMEZONES = {
    "A": ZoneInfo("Asia/Shanghai"),
    "US": ZoneInfo("America/New_York"),
}


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def get_market_timezone(market: str) -> ZoneInfo:
    return TIMEZONES[market]


def current_market_time(market: str, now: datetime | None = None) -> datetime:
    return _utc_now(now).astimezone(get_market_timezone(market))


def get_session_label(market: str, on_date: date) -> pd.Timestamp | None:
    calendar = CALENDARS[market]
    try:
        return calendar.date_to_session(pd.Timestamp(on_date), direction="none")
    except ValueError:
        return None


def get_current_session_label(market: str, now: datetime | None = None) -> pd.Timestamp | None:
    local_now = current_market_time(market, now)
    return get_session_label(market, local_now.date())


def is_market_open(market: str, now: datetime | None = None) -> bool:
    utc_now = _utc_now(now)
    session = get_current_session_label(market, utc_now)
    if session is None:
        return False

    calendar = CALENDARS[market]
    open_time = calendar.session_open(session)
    close_time = calendar.session_close(session)
    if utc_now < open_time or utc_now > close_time:
        return False

    if hasattr(calendar, "session_break_start") and hasattr(calendar, "session_break_end"):
        break_start = calendar.session_break_start(session)
        break_end = calendar.session_break_end(session)
        if break_start is not pd.NaT and break_end is not pd.NaT:
            if break_start <= utc_now <= break_end:
                return False

    return True


def trading_day_distance(market: str, start_day: date, end_day: date) -> int:
    if end_day < start_day:
        return 0
    calendar = CALENDARS[market]
    sessions = calendar.sessions_in_range(pd.Timestamp(start_day), pd.Timestamp(end_day))
    return max(len(sessions) - 1, 0)
