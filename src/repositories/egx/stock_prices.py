from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from datetime import time

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.structs import tables
from src.structs.enums import HistoryPeriods
from src.structs.models.responses import EGXStockDailyClose
from src.structs.models.responses import EGXStockPricePoint
from src.structs.models.responses import EGXStockQuote


CHUNK_SIZE = 1000


def _since(latest: object, period: HistoryPeriods) -> object:
    lookback = period.lookback

    return latest - func.make_interval(
        0, lookback.get("months", 0), lookback.get("weeks", 0)
    )


def _chunks[T](rows: list[T]) -> list[list[T]]:
    return [rows[i : i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]


async def insert_quotes(
    session: AsyncSession,
    quotes: Mapping[int, EGXStockQuote],
) -> int:
    rows = [
        {"stock_id": stock_id, **quote.model_dump()}
        for stock_id, quote in quotes.items()
    ]

    inserted = 0
    for chunk in _chunks(rows):
        result = await session.execute(
            insert(tables.EGXStockQuote)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=["stock_id", "quoted_at"])
            .returning(tables.EGXStockQuote.id),
        )
        inserted += len(result.all())

    return inserted


async def upsert_daily_prices(
    session: AsyncSession,
    closes: Mapping[int, Sequence[EGXStockDailyClose]],
) -> int:
    rows = [
        {"stock_id": stock_id, **close.model_dump()}
        for stock_id, stock_closes in closes.items()
        for close in stock_closes
    ]

    upserted = 0
    for chunk in _chunks(rows):
        statement = insert(tables.EGXStockDailyPrice).values(chunk)
        statement = statement.on_conflict_do_update(
            index_elements=["stock_id", "trade_date"],
            set_={
                "close_price": statement.excluded.close_price,
                "volume": statement.excluded.volume,
                "updated_at": func.now(),
            },
            where=tables.EGXStockDailyPrice.close_price.is_distinct_from(
                statement.excluded.close_price,
            )
            | tables.EGXStockDailyPrice.volume.is_distinct_from(
                statement.excluded.volume,
            ),
        ).returning(tables.EGXStockDailyPrice.id)
        upserted += len((await session.execute(statement)).all())

    return upserted


async def delete_quotes_before(session: AsyncSession, before: datetime) -> int:
    result = await session.execute(
        delete(tables.EGXStockQuote).where(tables.EGXStockQuote.quoted_at < before),
    )

    return result.rowcount


async def get_intraday_points(
    session: AsyncSession,
    stock_id: int,
    period: HistoryPeriods,
) -> list[EGXStockPricePoint]:
    quote = tables.EGXStockQuote
    of_stock = quote.stock_id == stock_id

    if period.sessions is not None:
        latest_sessions = (
            select(quote.trade_date)
            .where(of_stock)
            .distinct()
            .order_by(quote.trade_date.desc())
            .limit(period.sessions)
        )
        in_period = quote.trade_date.in_(latest_sessions)
    else:
        latest = select(func.max(quote.trade_date)).where(of_stock).scalar_subquery()
        in_period = quote.trade_date >= _since(latest, period)

    rows = await session.execute(
        select(quote.quoted_at, quote.last_price, quote.volume)
        .where(of_stock, in_period)
        .order_by(quote.quoted_at),
    )

    return [
        EGXStockPricePoint(timestamp=quoted_at, price=price, volume=volume)
        for quoted_at, price, volume in rows.tuples()
    ]


async def get_daily_points(
    session: AsyncSession,
    stock_id: int,
    period: HistoryPeriods,
    *,
    close_time: time,
    timezone: str,
) -> list[EGXStockPricePoint]:
    daily = tables.EGXStockDailyPrice
    of_stock = daily.stock_id == stock_id
    latest = select(func.max(daily.trade_date)).where(of_stock).scalar_subquery()

    rows = await session.execute(
        select(
            func.timezone(timezone, daily.trade_date + close_time),
            daily.close_price,
            daily.volume,
        )
        .where(of_stock, daily.trade_date >= _since(latest, period))
        .order_by(daily.trade_date),
    )

    return [
        EGXStockPricePoint(timestamp=timestamp, price=price, volume=volume)
        for timestamp, price, volume in rows.tuples()
    ]


async def get_daily_price_counts(session: AsyncSession) -> dict[int, int]:
    daily = tables.EGXStockDailyPrice
    rows = await session.execute(
        select(daily.stock_id, func.count()).group_by(daily.stock_id),
    )

    return dict(rows.tuples().all())
