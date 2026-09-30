from collections.abc import Mapping
from collections.abc import Sequence
from datetime import date
from datetime import datetime
from datetime import time

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.structs import tables
from src.structs.enums import HistoryPeriods
from src.structs.models.responses import EGXStockDailyClose
from src.structs.models.responses import EGXStockDailyPoint
from src.structs.models.responses import EGXStockPerformance
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
        daily = tables.EGXStockDailyPrice
        statement = insert(daily).values(chunk)
        excluded = statement.excluded
        kept = {
            column: func.coalesce(excluded[column], getattr(daily, column))
            for column in ("open_price", "high", "low")
        }
        statement = statement.on_conflict_do_update(
            index_elements=["stock_id", "trade_date"],
            set_={
                "close_price": excluded.close_price,
                "volume": excluded.volume,
                **kept,
                "updated_at": func.now(),
            },
            where=or_(
                daily.close_price.is_distinct_from(excluded.close_price),
                daily.volume.is_distinct_from(excluded.volume),
                *(
                    getattr(daily, column).is_distinct_from(value)
                    for column, value in kept.items()
                ),
            ),
        ).returning(daily.id)
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
) -> list[EGXStockDailyPoint]:
    daily = tables.EGXStockDailyPrice
    of_stock = daily.stock_id == stock_id
    latest = select(func.max(daily.trade_date)).where(of_stock).scalar_subquery()

    rows = await session.execute(
        select(
            func.timezone(timezone, daily.trade_date + close_time),
            daily.close_price,
            daily.volume,
            daily.open_price,
            daily.high,
            daily.low,
        )
        .where(of_stock, daily.trade_date >= _since(latest, period))
        .order_by(daily.trade_date),
    )

    return [
        EGXStockDailyPoint(
            timestamp=timestamp,
            price=price,
            volume=volume,
            open=open_price,
            high=high,
            low=low,
        )
        for timestamp, price, volume, open_price, high, low in rows.tuples()
    ]


async def get_daily_price_counts(session: AsyncSession) -> dict[int, int]:
    daily = tables.EGXStockDailyPrice
    rows = await session.execute(
        select(daily.stock_id, func.count()).group_by(daily.stock_id),
    )

    return dict(rows.tuples().all())


async def get_latest_trade_date(session: AsyncSession) -> date | None:
    return await session.scalar(select(func.max(tables.EGXStockDailyPrice.trade_date)))


async def get_stock_performance(
    session: AsyncSession,
    *,
    since: date,
    latest: date,
) -> list[EGXStockPerformance]:
    daily = tables.EGXStockDailyPrice

    def first_close(*where: object, newest: bool) -> object:
        return (
            select(daily.stock_id, daily.trade_date, daily.close_price)
            .where(daily.close_price.is_not(None), *where)
            .distinct(daily.stock_id)
            .order_by(
                daily.stock_id,
                daily.trade_date.desc() if newest else daily.trade_date,
            )
        )

    listed_since = await session.execute(
        first_close(daily.trade_date > since, daily.trade_date <= latest, newest=False),
    )
    bases = {stock_id: (day, price) for stock_id, day, price in listed_since.tuples()}
    by_start = await session.execute(
        first_close(daily.trade_date <= since, newest=True)
    )
    bases |= {stock_id: (day, price) for stock_id, day, price in by_start.tuples()}

    value = daily.volume * daily.close_price
    before_latest = daily.trade_date < latest
    on_latest = daily.trade_date == latest
    traded = await session.execute(
        select(
            daily.stock_id,
            func.coalesce(func.sum(daily.volume).filter(before_latest), 0),
            func.coalesce(func.sum(value).filter(before_latest), 0),
            func.coalesce(func.sum(daily.volume).filter(on_latest), 0),
            func.coalesce(func.sum(value).filter(on_latest), 0),
        )
        .where(daily.trade_date > since, daily.trade_date <= latest)
        .group_by(daily.stock_id),
    )
    sums = {
        stock_id: {
            "volume": volume,
            "value": value,
            "latest_volume": latest_volume,
            "latest_value": latest_value,
        }
        for stock_id, volume, value, latest_volume, latest_value in traded.tuples()
    }
    nothing = dict.fromkeys(("volume", "value", "latest_volume", "latest_value"), 0)

    isins = await session.execute(
        select(tables.EGXStock.id, tables.EGXStock.isin)
        .where(tables.EGXStock.id.in_(bases))
        .order_by(tables.EGXStock.isin),
    )

    return [
        EGXStockPerformance(
            isin=isin,
            base_date=bases[stock_id][0],
            base_close=bases[stock_id][1],
            **sums.get(stock_id, nothing),
        )
        for stock_id, isin in isins.tuples()
    ]
