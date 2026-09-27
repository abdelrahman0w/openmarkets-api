from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from src.exceptions import ExchangeError
from src.providers import logger
from src.services import EGXService
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.enums import EGXMarketStatusValue
from src.structs.enums import MarketDayStatuses
from src.utils import is_market_open
from src.utils import single_flight


def _seconds_until_midnight(now: datetime) -> int:
    local = now.astimezone(ZoneInfo(settings.egx_market.timezone))
    midnight = datetime.combine(
        local.date() + timedelta(days=1),
        datetime.min.time(),
        local.tzinfo,
    )

    return max(60, int((midnight - local).total_seconds()))


def _local_day(now: datetime) -> str:
    return (
        now.astimezone(
            ZoneInfo(settings.egx_market.timezone),
        )
        .date()
        .isoformat()
    )


async def _ask_egx(
    now: datetime,
    egx: EGXService,
    redis: Redis,
    *,
    day_key: str,
    retry_key: str,
) -> bool:
    market = settings.egx_market
    until_midnight = _seconds_until_midnight(now)

    try:
        status = (await egx.market_status()).status
    except ExchangeError:
        logger.warning(
            "[Market Status] Could Not Ask EGX - Going By The Trading Hours",
        )

        await redis.set(
            retry_key,
            MarketDayStatuses.UNKNOWN,
            ex=market.status_retry_seconds,
        )

        return True

    if status == EGXMarketStatusValue.OPEN:
        await redis.set(
            day_key,
            MarketDayStatuses.OPEN,
            ex=until_midnight,
        )

        return True

    session_open = datetime.combine(
        now.astimezone(ZoneInfo(market.timezone)).date(),
        market.open_time,
        ZoneInfo(market.timezone),
    )
    if now < session_open + timedelta(minutes=market.status_retry_minutes):
        await redis.set(
            retry_key,
            MarketDayStatuses.CLOSED,
            ex=market.status_retry_seconds,
        )
    else:
        await redis.set(
            day_key,
            MarketDayStatuses.CLOSED,
            ex=until_midnight,
        )

    return False


async def is_egx_market_open(
    now: datetime,
    egx: EGXService,
    redis: Redis,
    *,
    with_grace: bool = False,
) -> bool:
    market = settings.egx_market
    hours = {
        "timezone": market.timezone,
        "open_time": market.open_time,
        "close_time": market.close_time,
        "trading_days": market.trading_days,
    }

    in_session = is_market_open(now, **hours)
    grace = timedelta(minutes=market.sync_grace_minutes)
    if not in_session and not (
        with_grace and is_market_open(now, grace=grace, **hours)
    ):
        return False

    if not market.use_live_status:
        return True

    day = _local_day(now)
    day_key = CacheKeys.EGX_MARKET_DAY.format(day=day)
    retry_key = CacheKeys.EGX_MARKET_DAY_RETRY.format(day=day)

    if (status := await redis.get(day_key)) is not None:
        return status == MarketDayStatuses.OPEN

    if not in_session:
        return False

    if (retry := await redis.get(retry_key)) is not None:
        return retry == MarketDayStatuses.UNKNOWN

    return await single_flight(
        day_key,
        lambda: _ask_egx(now, egx, redis, day_key=day_key, retry_key=retry_key),
    )
