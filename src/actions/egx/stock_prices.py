import asyncio
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.actions import cached_json
from src.actions.egx import cache_stocks
from src.actions.egx import is_egx_market_open
from src.exceptions import ExchangeError
from src.providers import logger
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.models.requests import EGXPriceVolumePointsRequest
from src.structs.models.responses import EGXPriceVolumePoint
from src.structs.models.responses import EGXStock
from src.structs.models.responses import EGXStockDailyClose
from src.structs.models.responses import is_common_stock


async def fetch_live_stocks(egx: EGXService) -> list[EGXStock]:
    return [
        EGXStock.from_market_watch_row(row)
        for row in await egx.stock_board()
        if is_common_stock(row)
    ]


async def store_stocks(session: AsyncSession, stocks: Sequence[EGXStock]) -> int:
    stock_ids = await egx_repositories.upsert_stocks(session, stocks)
    quotes = {stock_ids[stock.isin]: stock.quote for stock in stocks if stock.quote}

    inserted = await egx_repositories.insert_quotes(session, quotes)

    await egx_repositories.upsert_daily_prices(
        session,
        {
            stock_id: [
                EGXStockDailyClose(
                    trade_date=quote.trade_date,
                    close_price=quote.last_price,
                    volume=quote.volume,
                ),
            ]
            for stock_id, quote in quotes.items()
            if quote.trade_date is not None
        },
    )

    return inserted


async def sync_stock_prices(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    now: datetime,
    force: bool = False,
) -> int | None:
    if not force and not await is_egx_market_open(now, egx, redis, with_grace=True):
        logger.debug(
            "[Stock Prices] Sync Skipped - The Market Is Closed",
        )

        return None

    stocks = await fetch_live_stocks(egx)
    await cache_stocks(redis, stocks)

    async with session_factory() as session, session.begin():
        inserted = await store_stocks(session, stocks)

    logger.info(
        "[Stock Prices] Synced",
        stocks=len(stocks),
        new_quotes=inserted,
    )

    return inserted


async def get_live_stocks(egx: EGXService, redis: Redis) -> str:
    async def fetch() -> list[EGXStock]:
        stocks = await fetch_live_stocks(egx)
        await cache_stocks(redis, stocks)

        return stocks

    return await cached_json(
        redis,
        CacheKeys.EGX_LIVE_STOCKS,
        fetch,
        list[EGXStock],
        ttl_seconds=settings.egx_market.live_prices_cache_seconds,
    )


async def prune_stock_quotes(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
) -> int:
    before = now - timedelta(days=settings.egx_market.quote_retention_days)

    async with session_factory() as session, session.begin():
        deleted = await egx_repositories.delete_quotes_before(session, before)

    logger.info(
        "[Stock Prices] Quotes Pruned",
        deleted=deleted,
        before=before.isoformat(),
    )

    return deleted


async def backfill_stock_prices(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    days: int,
    isins: Sequence[str] | None = None,
    missing_only: bool = False,
    concurrency: int = 2,
    pause_seconds: float = 1.0,
    retries: int = 3,
) -> dict[str, int]:
    stocks = await fetch_live_stocks(egx)

    async with session_factory() as session, session.begin():
        await store_stocks(session, stocks)
        stock_ids = await egx_repositories.get_stock_ids(session)
        history_sizes = await egx_repositories.get_daily_price_counts(session)

    wanted = set(isins) if isins else set(stock_ids)
    if unknown := wanted - set(stock_ids):
        logger.warning(
            "[Stock Prices] Backfill Skipped Unknown Stocks",
            isins=sorted(unknown),
        )

    if missing_only:
        wanted = {
            isin
            for isin in wanted
            if history_sizes.get(stock_ids.get(isin, -1), 0) <= 1
        }

    semaphore = asyncio.Semaphore(concurrency)
    stored: dict[str, int] = {}
    failed: list[str] = []

    async def fetch(isin: str) -> list[EGXPriceVolumePoint] | None:
        for attempt in range(retries + 1):
            async with semaphore:
                try:
                    return await egx.price_volume_points(
                        EGXPriceVolumePointsRequest(isin=isin, days=days),
                    )
                except ExchangeError:
                    if attempt == retries:
                        logger.exception(
                            "[Stock Prices] Could Not Fetch Price History",
                            isin=isin,
                        )

                        return None
                finally:
                    await asyncio.sleep(pause_seconds)

            backoff = pause_seconds * 5 * 3**attempt
            logger.warning(
                "[Stock Prices] Retrying Price History",
                isin=isin,
                attempt=attempt + 1,
                backoff_seconds=backoff,
            )

            await asyncio.sleep(backoff)

        return None

    async def backfill(isin: str, stock_id: int) -> None:
        points = await fetch(isin)
        if points is None:
            failed.append(isin)

            return

        closes = [
            EGXStockDailyClose(
                trade_date=point.trade_date,
                close_price=point.close_price,
                volume=point.trade_volume,
            )
            for point in points
            if point.trade_date is not None
        ]

        async with session_factory() as session, session.begin():
            stored[isin] = await egx_repositories.upsert_daily_prices(
                session,
                {stock_id: closes},
            )

    async with asyncio.TaskGroup() as group:
        for isin in sorted(wanted & set(stock_ids)):
            group.create_task(backfill(isin, stock_ids[isin]))

    logger.info(
        "[Stock Prices] Backfilled",
        stocks=len(stored),
        daily_prices=sum(stored.values()),
        failed=sorted(failed),
        days=days,
    )

    return stored
