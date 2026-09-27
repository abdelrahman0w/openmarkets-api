from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions import cached_json
from src.actions import egx as egx_actions
from src.exceptions import NotFoundError
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.enums import HistoryPeriods
from src.structs.enums import PriceIntervals
from src.structs.models.responses import EGXStock
from src.structs.models.responses import EGXStockHistory
from src.utils import single_flight


async def _load_stocks(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
) -> tuple[str, list[EGXStock]]:
    async def load() -> tuple[str, list[EGXStock]]:
        stocks = await egx_repositories.get_stocks(session)
        if not stocks:
            stocks = await egx_actions.fetch_live_stocks(egx)

        return await egx_actions.cache_stocks(redis, stocks), stocks

    return await single_flight("egx:stocks:load", load)


async def list_stocks(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
    *,
    now: datetime,
) -> str:
    if await egx_actions.is_egx_market_open(now, egx, redis):
        return await egx_actions.get_live_stocks(egx, redis)

    if (cached := await egx_actions.get_cached_stocks(redis)) is not None:
        return cached

    listing, _ = await _load_stocks(egx, session, redis)

    return listing


async def get_stock(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
    *,
    isin: str,
    now: datetime,
) -> str:
    if await egx_actions.is_egx_market_open(now, egx, redis):
        await egx_actions.get_live_stocks(egx, redis)

    cached, stock = await egx_actions.get_cached_stock(redis, isin)

    if not cached:
        _, stocks = await _load_stocks(egx, session, redis)
        found = next((each for each in stocks if each.isin == isin), None)
        stock = found.model_dump_json() if found else None

    if stock is None:
        raise NotFoundError(f"Stock {isin} was not found")

    return stock


async def get_stock_history(
    session: AsyncSession,
    redis: Redis,
    *,
    isin: str,
    period: HistoryPeriods,
) -> str:
    async def history() -> EGXStockHistory:
        stock_id = await egx_repositories.get_stock_id(session, isin)
        if stock_id is None:
            raise NotFoundError(f"Stock {isin} was not found")

        if period.interval is PriceIntervals.ONE_MINUTE:
            points = await egx_repositories.get_intraday_points(
                session,
                stock_id,
                period,
            )
        else:
            points = await egx_repositories.get_daily_points(
                session,
                stock_id,
                period,
                close_time=settings.egx_market.close_time,
                timezone=settings.egx_market.timezone,
            )

        return EGXStockHistory(
            isin=isin,
            period=period,
            interval=period.interval,
            points=points,
        )

    return await cached_json(
        redis,
        CacheKeys.EGX_STOCK_HISTORY.format(isin=isin, period=period),
        history,
        EGXStockHistory,
        ttl_seconds=settings.redis.cache_ttl_seconds,
    )
