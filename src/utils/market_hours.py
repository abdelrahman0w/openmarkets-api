from collections.abc import Collection
from datetime import datetime
from datetime import time
from datetime import timedelta
from zoneinfo import ZoneInfo


def is_market_open(
    now: datetime,
    *,
    timezone: str,
    open_time: time,
    close_time: time,
    trading_days: Collection[int],
    grace: timedelta = timedelta(0),
) -> bool:
    local_now = now.astimezone(ZoneInfo(timezone))
    if local_now.weekday() not in trading_days:
        return False

    session_open = datetime.combine(
        date=local_now.date(),
        time=open_time,
        tzinfo=local_now.tzinfo,
    )
    session_close = datetime.combine(
        date=local_now.date(),
        time=close_time,
        tzinfo=local_now.tzinfo,
    )

    return session_open <= local_now < session_close + grace


def seconds_until_next_boundary(
    now: datetime,
    *,
    timezone: str,
    open_time: time,
    close_time: time,
    trading_days: Collection[int],
) -> float:
    local_now = now.astimezone(ZoneInfo(timezone))

    for offset in range(8):
        day = local_now.date() + timedelta(days=offset)
        if day.weekday() not in trading_days:
            continue

        for moment in (open_time, close_time):
            boundary = datetime.combine(day, moment, local_now.tzinfo)
            if boundary > local_now:
                return (boundary - local_now).total_seconds()

    raise ValueError("no trading days are configured")
