import asyncio
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.actions.egx.market_hours import is_egx_market_open
from src.exceptions import ExchangeBlockedError
from src.exceptions import ExchangeError
from src.providers import logger
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.models import Page
from src.structs.models.requests import EGXNewsSearchRequest
from src.structs.models.responses import EGXNewsItem


async def _store_page(
    session_factory: async_sessionmaker[AsyncSession],
    page: Page[EGXNewsItem],
) -> tuple[int, int]:
    codes = {item.code for item in page.items if item.code is not None}

    async with session_factory() as session, session.begin():
        known = await egx_repositories.get_known_news_codes(session, codes)
        changed = await egx_repositories.upsert_news(session, page.items)

    return len(codes - known), changed


def _is_sync_due(now: datetime, *, in_session: bool) -> bool:
    news = settings.egx_news
    every = news.sync_session_minutes if in_session else news.sync_off_session_minutes
    local = now.astimezone(ZoneInfo(settings.egx_market.timezone))

    return (local.hour * 60 + local.minute) % every == 0


async def sync_news(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    now: datetime,
    force: bool = False,
    delay_seconds: float = 0,
) -> int | None:
    news = settings.egx_news
    in_session = await is_egx_market_open(now, egx, redis)

    if not force and not _is_sync_due(now, in_session=in_session):
        logger.debug(
            "[News] Sync Skipped - Not Due",
            in_session=in_session,
        )

        return None

    await asyncio.sleep(delay_seconds)

    async with session_factory() as session:
        max_pages = (
            news.sync_max_pages if await egx_repositories.has_news(session) else 1
        )

    new = changed = pages = 0
    for page_number in range(1, max_pages + 1):
        if page_number > 1:
            await asyncio.sleep(news.sync_pause_seconds)

        page = await egx.news_search(
            EGXNewsSearchRequest(
                page_number=page_number,
                page_size=news.sync_page_size,
            ),
        )
        page_new, page_changed = await _store_page(session_factory, page)
        new, changed, pages = new + page_new, changed + page_changed, pages + 1

        page_is_full = len(page.items) >= news.sync_page_size
        if page_new < len(page.items) or not page_is_full:
            break
        if page_number >= (page.total_pages or 1):
            break

    logger.info(
        "[News] Synced",
        pages=pages,
        new=new,
        changed=changed,
        in_session=in_session,
    )

    return new


async def backfill_news(
    egx: EGXService,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    days: int,
    page_size: int = 250,
    from_page: int = 1,
    pause_seconds: float = 3.0,
    retries: int = 3,
) -> int:
    today = now.astimezone(ZoneInfo(settings.egx_market.timezone)).date()
    date_from = today - timedelta(days=days)

    async def fetch(page_number: int) -> Page[EGXNewsItem] | None:
        for attempt in range(retries + 1):
            try:
                return await egx.news_search(
                    EGXNewsSearchRequest(
                        page_number=page_number,
                        page_size=page_size,
                        date_from=date_from,
                        date_to=today,
                    ),
                )
            except ExchangeBlockedError:
                logger.error(
                    "[News] Backfill Stopped - EGX Is Blocking Requests",
                    page=page_number,
                )

                return None
            except ExchangeError:
                if attempt == retries:
                    logger.exception(
                        "[News] Backfill Stopped - Could Not Fetch A Page",
                        page=page_number,
                    )

                    return None

            backoff = pause_seconds * 5 * 3**attempt

            logger.warning(
                "[News] Retrying A Page",
                page=page_number,
                attempt=attempt + 1,
                backoff_seconds=backoff,
            )

            await asyncio.sleep(backoff)

        return None

    new = 0
    page_number = from_page
    total_pages: int | None = None

    while total_pages is None or page_number <= total_pages:
        page = await fetch(page_number)
        if page is None:
            break

        page_new, _ = await _store_page(session_factory, page)
        new += page_new
        total_pages = page.total_pages or page_number

        logger.info(
            "[News] Backfilled A Page",
            page=page_number,
            total_pages=total_pages,
            new=page_new,
        )

        page_number += 1
        await asyncio.sleep(pause_seconds)

    logger.info(
        "[News] Backfilled",
        new=new,
        days=days,
        last_page=page_number - 1,
        total_pages=total_pages,
    )

    return new
