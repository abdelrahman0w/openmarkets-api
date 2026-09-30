import asyncio
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.actions.egx.market_hours import is_egx_market_open
from src.exceptions import ExchangeBlockedError
from src.exceptions import ExchangeError
from src.providers import logger
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.enums import CacheKeys
from src.structs.enums import EGXIndexName
from src.structs.models import Page
from src.structs.models.requests import EGXIndexDataRequest
from src.structs.models.requests import EGXIndexHistoryRequest
from src.structs.models.responses import EGXIndexDailyBar


def _is_sync_due(now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(settings.egx_market.timezone))

    return (
        local.hour * 60 + local.minute
    ) % settings.egx_indices.sync_every_minutes == 0


async def sync_indices(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    now: datetime,
    force: bool = False,
    delay_seconds: float = 0,
) -> int | None:
    indices = settings.egx_indices

    if not force and not (
        _is_sync_due(now) and await is_egx_market_open(now, egx, redis, with_grace=True)
    ):
        logger.debug(
            "[Indices] Sync Skipped - Not Due Or The Market Is Closed",
        )

        return None

    await asyncio.sleep(delay_seconds)

    points = 0
    synced: list[str] = []
    failed: list[str] = []
    for position, index in enumerate(EGXIndexName):
        if position:
            await asyncio.sleep(indices.sync_pause_seconds)

        try:
            data = await egx.index_data(EGXIndexDataRequest(index=index))
        except ExchangeBlockedError:
            logger.error(
                "[Indices] Sync Stopped - EGX Is Blocking Requests",
                index=index,
            )

            break
        except ExchangeError:
            logger.warning(
                "[Indices] Could Not Fetch An Index",
                index=index,
            )

            failed.append(index)

            continue

        async with session_factory() as session, session.begin():
            if data.live is not None and data.live.day is not None:
                await egx_repositories.upsert_index_bars(
                    session,
                    index,
                    [EGXIndexDailyBar.model_validate(data.live.model_dump())],
                    ytd_percent=data.live.ytd_percent,
                )

            points += await egx_repositories.insert_index_points(
                session,
                index,
                data.intraday,
            )

        synced.append(index)

    async with session_factory() as session, session.begin():
        await egx_repositories.delete_index_points_before(
            session,
            now - timedelta(days=indices.point_retention_days),
        )

    try:
        await redis.delete(CacheKeys.EGX_INDEX_LEVELS)
    except RedisError:
        logger.warning(
            "[Indices] Could Not Clear The Cached Levels - Redis Is Unavailable",
        )

    logger.info(
        "[Indices] Synced",
        indices=len(synced),
        new_points=points,
        failed=failed,
    )

    return points


async def backfill_indices(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    indices: Sequence[EGXIndexName] | None = None,
    missing_only: bool = False,
    page_size: int = 250,
    pause_seconds: float = 3.0,
    retries: int = 3,
) -> dict[str, int]:
    async with session_factory() as session:
        counts = await egx_repositories.get_index_bar_counts(session)

    wanted = list(indices or EGXIndexName)
    if missing_only:
        wanted = [index for index in wanted if counts.get(index, 0) <= 1]

    blocked = False

    async def fetch(
        index: EGXIndexName, page_number: int
    ) -> Page[EGXIndexDailyBar] | None:
        nonlocal blocked

        for attempt in range(retries + 1):
            try:
                return await egx.index_history(
                    EGXIndexHistoryRequest(
                        index=index,
                        page_number=page_number,
                        page_size=page_size,
                    ),
                )
            except ExchangeBlockedError:
                blocked = True

                logger.error(
                    "[Indices] Backfill Stopped - EGX Is Blocking Requests",
                    index=index,
                    page=page_number,
                )

                return None
            except ExchangeError:
                if attempt == retries:
                    logger.exception(
                        "[Indices] Could Not Fetch A Page",
                        index=index,
                        page=page_number,
                    )

                    return None

            backoff = pause_seconds * 5 * 3**attempt

            logger.warning(
                "[Indices] Retrying A Page",
                index=index,
                page=page_number,
                attempt=attempt + 1,
                backoff_seconds=backoff,
            )

            await asyncio.sleep(backoff)

        return None

    stored: dict[str, int] = {}

    for index in wanted:
        page_number, total_pages = 1, None
        stored[index.value] = 0

        while not blocked and (total_pages is None or page_number <= total_pages):
            page = await fetch(index, page_number)
            if page is None:
                break

            async with session_factory() as session, session.begin():
                stored[index.value] += await egx_repositories.upsert_index_bars(
                    session,
                    index,
                    page.items,
                )

            total_pages = page.total_pages or page_number
            page_number += 1

            await asyncio.sleep(pause_seconds)

        if blocked:
            break

    logger.info(
        "[Indices] Backfilled",
        bars=stored,
        blocked=blocked,
    )

    return stored
