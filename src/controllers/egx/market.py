from datetime import datetime

from redis.asyncio import Redis

from src.actions import cached_live_json
from src.actions import egx as egx_actions
from src.services import EGXService
from src.structs.enums import EGXMarketStatusValue
from src.structs.models import Page
from src.structs.models.requests import EGXDerivativesWatchRequest
from src.structs.models.requests import EGXPriceVolumePointsRequest
from src.structs.models.requests import EGXStockMarketWatchRequest
from src.structs.models.responses import EGXDerivativeWatchRow
from src.structs.models.responses import EGXMarketIndicator
from src.structs.models.responses import EGXMarketStatus
from src.structs.models.responses import EGXMarketSummaries
from src.structs.models.responses import EGXMetalQuote
from src.structs.models.responses import EGXPriceVolumePoint
from src.structs.models.responses import EGXStockMarketWatchRow


async def get_market_status(
    egx: EGXService,
    redis: Redis,
    *,
    now: datetime,
) -> str:
    is_open = await egx_actions.is_egx_market_open(now, egx, redis)

    return EGXMarketStatus(
        status=EGXMarketStatusValue.OPEN if is_open else EGXMarketStatusValue.CLOSED,
        status_datetime=now,
    ).model_dump_json()


async def get_stock_market_watch(
    egx: EGXService,
    redis: Redis,
    request: EGXStockMarketWatchRequest,
) -> str:
    return await cached_live_json(
        redis,
        "stocks",
        lambda: egx.stock_market_watch(request),
        Page[EGXStockMarketWatchRow],
        request,
    )


async def get_gold_market_watch(
    egx: EGXService,
    redis: Redis,
) -> str:
    return await cached_live_json(
        redis,
        "gold",
        egx.gold_market_watch,
        list[EGXMetalQuote],
    )


async def get_silver_market_watch(
    egx: EGXService,
    redis: Redis,
) -> str:
    return await cached_live_json(
        redis,
        "silver",
        egx.silver_market_watch,
        list[EGXMetalQuote],
    )


async def get_derivatives_watch(
    egx: EGXService,
    redis: Redis,
    request: EGXDerivativesWatchRequest,
) -> str:
    return await cached_live_json(
        redis,
        "derivatives",
        lambda: egx.derivatives_watch(request),
        Page[EGXDerivativeWatchRow],
        request,
    )


async def get_price_volume_points(
    egx: EGXService,
    redis: Redis,
    request: EGXPriceVolumePointsRequest,
) -> str:
    return await cached_live_json(
        redis,
        "price-volume-points",
        lambda: egx.price_volume_points(request),
        list[EGXPriceVolumePoint],
        request,
    )


async def get_market_summaries(egx: EGXService, redis: Redis) -> str:
    return await cached_live_json(
        redis,
        "summaries",
        egx.market_summaries,
        EGXMarketSummaries,
    )


async def get_market_indicators(egx: EGXService, redis: Redis) -> str:
    return await cached_live_json(
        redis,
        "indicators",
        egx.market_indicators,
        list[EGXMarketIndicator],
    )
