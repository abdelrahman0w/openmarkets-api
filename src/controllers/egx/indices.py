from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions import cached_json
from src.actions import cached_live_json
from src.exceptions import NotFoundError
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.enums import EGXIndexName
from src.structs.enums import HistoryPeriods
from src.structs.enums import PerformancePeriods
from src.structs.enums import PriceIntervals
from src.structs.models.requests import EGXIndexSummaryRequest
from src.structs.models.responses import EGXIndexHistory
from src.structs.models.responses import EGXIndexLevel
from src.structs.models.responses import EGXIndexSummary
from src.structs.models.responses import EGXIndexWeight
from src.structs.models.responses import EGXIndicesPerformance


def _index(code: str) -> EGXIndexName:
    try:
        return EGXIndexName(code)
    except ValueError:
        raise NotFoundError(f"Index {code} was not found") from None


async def list_indices(
    session: AsyncSession,
    redis: Redis,
) -> str:
    return await cached_json(
        redis,
        CacheKeys.EGX_INDEX_LEVELS,
        lambda: egx_repositories.get_index_levels(
            session,
            timezone=settings.egx_market.timezone,
        ),
        list[EGXIndexLevel],
        ttl_seconds=settings.egx_indices.levels_cache_seconds,
    )


async def get_indices_performance(
    session: AsyncSession,
    redis: Redis,
    *,
    period: PerformancePeriods,
) -> str:
    async def performance() -> EGXIndicesPerformance:
        latest = await egx_repositories.get_latest_index_day(session)
        if latest is None:
            return EGXIndicesPerformance(period=period)

        since = period.since(latest)

        return EGXIndicesPerformance(
            period=period,
            since=since,
            indices=await egx_repositories.get_index_performance(
                session,
                since=since,
                latest=latest,
            ),
        )

    return await cached_json(
        redis,
        CacheKeys.EGX_INDICES_PERFORMANCE.format(period=period),
        performance,
        EGXIndicesPerformance,
        ttl_seconds=settings.redis.cache_ttl_seconds,
    )


async def get_index_history(
    session: AsyncSession,
    redis: Redis,
    *,
    code: str,
    period: HistoryPeriods,
) -> str:
    index = _index(code)

    async def history() -> EGXIndexHistory:
        market = settings.egx_market
        if period.interval is PriceIntervals.ONE_MINUTE:
            points = await egx_repositories.get_index_intraday_points(
                session,
                index,
                period,
                timezone=market.timezone,
            )
        else:
            points = await egx_repositories.get_index_daily_points(
                session,
                index,
                period,
                close_time=market.close_time,
                timezone=market.timezone,
            )

        return EGXIndexHistory(
            index=index,
            period=period,
            interval=period.interval,
            points=points,
        )

    return await cached_json(
        redis,
        CacheKeys.EGX_INDEX_HISTORY.format(index=index, period=period),
        history,
        EGXIndexHistory,
        ttl_seconds=settings.redis.cache_ttl_seconds,
    )


async def get_index_summary(
    egx: EGXService,
    redis: Redis,
    *,
    code: str,
) -> str:
    index = _index(code)
    if index is EGXIndexName.EGX30_USD:
        index = EGXIndexName.EGX30

    request = EGXIndexSummaryRequest(index=index)

    return await cached_live_json(
        redis,
        "index-summary",
        lambda: egx.index_summary(request),
        EGXIndexSummary,
        request,
        ttl_seconds=settings.egx_indices.summary_cache_seconds,
        fresh_seconds=settings.egx_indices.summary_fresh_seconds,
    )


async def get_index_weights(
    egx: EGXService,
    redis: Redis,
    *,
    code: str,
) -> str:
    if _index(code) is not EGXIndexName.EGX30:
        raise NotFoundError(f"Index {code} has no published weights")

    return await cached_live_json(
        redis,
        "egx30-weights",
        egx.egx30_weights,
        list[EGXIndexWeight],
        ttl_seconds=settings.egx_indices.weights_cache_seconds,
        fresh_seconds=settings.egx_indices.weights_fresh_seconds,
    )
