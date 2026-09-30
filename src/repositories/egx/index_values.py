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
from src.structs.enums import EGX_INDEX_TITLES
from src.structs.enums import EGXIndexName
from src.structs.enums import HistoryPeriods
from src.structs.models.responses import EGXIndexDailyBar
from src.structs.models.responses import EGXIndexDailyPoint
from src.structs.models.responses import EGXIndexIntradayPoint
from src.structs.models.responses import EGXIndexLevel
from src.structs.models.responses import EGXIndexPerformance
from src.structs.models.responses import EGXIndexValuePoint


CHUNK_SIZE = 1000
BAR_COLUMNS = ("open", "high", "low", "close", "change", "change_percent")


def _since(latest: object, period: HistoryPeriods) -> object:
    lookback = period.lookback

    return latest - func.make_interval(
        0, lookback.get("months", 0), lookback.get("weeks", 0)
    )


def _local_day(timezone: str) -> object:
    return func.date(func.timezone(timezone, tables.EGXIndexPoint.timestamp))


async def upsert_index_bars(
    session: AsyncSession,
    index: EGXIndexName,
    bars: Sequence[EGXIndexDailyBar],
    *,
    ytd_percent: float | None = None,
) -> int:
    rows = [
        {"index": index, "day": bar.day, **bar.model_dump(include=set(BAR_COLUMNS))}
        for bar in bars
        if bar.day is not None
    ]

    if ytd_percent is not None:
        for row in rows:
            row["ytd_percent"] = ytd_percent

    bar = tables.EGXIndexDailyBar
    columns = [*BAR_COLUMNS, *(("ytd_percent",) if ytd_percent is not None else ())]

    upserted = 0
    for start in range(0, len(rows), CHUNK_SIZE):
        statement = insert(bar).values(rows[start : start + CHUNK_SIZE])
        statement = statement.on_conflict_do_update(
            index_elements=["index", "day"],
            set_={
                **{column: statement.excluded[column] for column in columns},
                "updated_at": func.now(),
            },
            where=or_(
                *(
                    getattr(bar, column).is_distinct_from(statement.excluded[column])
                    for column in columns
                ),
            ),
        ).returning(bar.id)
        upserted += len((await session.execute(statement)).all())

    return upserted


async def insert_index_points(
    session: AsyncSession,
    index: EGXIndexName,
    points: Sequence[EGXIndexIntradayPoint],
) -> int:
    rows = [
        {"index": index, "timestamp": point.timestamp, "value": point.value}
        for point in points
        if point.timestamp is not None and point.value is not None
    ]
    if not rows:
        return 0

    result = await session.execute(
        insert(tables.EGXIndexPoint)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["index", "timestamp"])
        .returning(tables.EGXIndexPoint.id),
    )

    return len(result.all())


async def delete_index_points_before(session: AsyncSession, before: datetime) -> int:
    result = await session.execute(
        delete(tables.EGXIndexPoint).where(tables.EGXIndexPoint.timestamp < before),
    )

    return result.rowcount


async def get_index_levels(
    session: AsyncSession,
    *,
    timezone: str,
) -> list[EGXIndexLevel]:
    bar = tables.EGXIndexDailyBar
    point = tables.EGXIndexPoint

    latest_bars = (
        await session.scalars(
            select(bar).distinct(bar.index).order_by(bar.index, bar.day.desc()),
        )
    ).all()
    by_index = {row.index: row for row in latest_bars}
    latest_day = (
        select(func.max(bar.day)).where(bar.index == point.index).scalar_subquery()
    )
    points = await session.execute(
        select(point.index, point.timestamp, point.value)
        .where(_local_day(timezone) == latest_day)
        .order_by(point.index, point.timestamp),
    )
    points_by_index: dict[str, list[EGXIndexValuePoint]] = {}

    for index, timestamp, value in points.tuples():
        points_by_index.setdefault(index, []).append(
            EGXIndexValuePoint(timestamp=timestamp, value=value),
        )

    return [
        EGXIndexLevel(
            index=index,
            title=EGX_INDEX_TITLES[index],
            day=row.day,
            **{
                column: getattr(row, column) for column in (*BAR_COLUMNS, "ytd_percent")
            },
            points=points_by_index.get(index, []),
        )
        for index in EGXIndexName
        if (row := by_index.get(index)) is not None
    ]


async def get_index_intraday_points(
    session: AsyncSession,
    index: EGXIndexName,
    period: HistoryPeriods,
    *,
    timezone: str,
) -> list[EGXIndexValuePoint]:
    point = tables.EGXIndexPoint
    of_index = point.index == index
    local_day = _local_day(timezone)

    if period.sessions is not None:
        latest_sessions = (
            select(local_day)
            .where(of_index)
            .distinct()
            .order_by(local_day.desc())
            .limit(period.sessions)
        )
        in_period = local_day.in_(latest_sessions)
    else:
        latest = select(func.max(point.timestamp)).where(of_index).scalar_subquery()
        in_period = point.timestamp >= _since(latest, period)

    rows = await session.execute(
        select(point.timestamp, point.value)
        .where(of_index, in_period)
        .order_by(point.timestamp),
    )

    return [
        EGXIndexValuePoint(timestamp=timestamp, value=value)
        for timestamp, value in rows.tuples()
    ]


async def get_index_daily_points(
    session: AsyncSession,
    index: EGXIndexName,
    period: HistoryPeriods,
    *,
    close_time: time,
    timezone: str,
) -> list[EGXIndexDailyPoint]:
    bar = tables.EGXIndexDailyBar
    of_index = bar.index == index
    latest = select(func.max(bar.day)).where(of_index).scalar_subquery()
    rows = await session.execute(
        select(
            func.timezone(timezone, bar.day + close_time),
            bar.close,
            bar.open,
            bar.high,
            bar.low,
        )
        .where(of_index, bar.day >= _since(latest, period))
        .order_by(bar.day),
    )

    return [
        EGXIndexDailyPoint(
            timestamp=timestamp,
            value=value,
            open=open_,
            high=high,
            low=low,
        )
        for timestamp, value, open_, high, low in rows.tuples()
    ]


async def get_index_bar_counts(session: AsyncSession) -> dict[str, int]:
    bar = tables.EGXIndexDailyBar
    rows = await session.execute(select(bar.index, func.count()).group_by(bar.index))

    return dict(rows.tuples().all())


async def get_latest_index_day(session: AsyncSession) -> date | None:
    return await session.scalar(select(func.max(tables.EGXIndexDailyBar.day)))


async def get_index_performance(
    session: AsyncSession,
    *,
    since: date,
    latest: date,
) -> list[EGXIndexPerformance]:
    bar = tables.EGXIndexDailyBar

    def first_close(*where: object, newest: bool) -> object:
        return (
            select(bar.index, bar.day, bar.close)
            .where(bar.close.is_not(None), *where)
            .distinct(bar.index)
            .order_by(bar.index, bar.day.desc() if newest else bar.day)
        )

    started_since = await session.execute(
        first_close(bar.day > since, bar.day <= latest, newest=False),
    )
    bases = {index: (day, close) for index, day, close in started_since.tuples()}
    by_start = await session.execute(first_close(bar.day <= since, newest=True))
    bases |= {index: (day, close) for index, day, close in by_start.tuples()}

    return [
        EGXIndexPerformance(
            index=index,
            base_date=bases[index][0],
            base_close=bases[index][1],
        )
        for index in EGXIndexName
        if index in bases
    ]
