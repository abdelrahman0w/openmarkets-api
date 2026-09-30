import asyncio
import html
import math
import re
from datetime import datetime
from datetime import time
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from openmarkets.exchanges.egx.settings import egx_settings
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.exceptions import SummarizerBusyError
from src.exceptions import SummarizerError
from src.providers import logger
from src.repositories import egx as egx_repositories
from src.services import GeminiService
from src.settings import settings
from src.structs import tables
from src.structs.enums import CacheKeys


PDF_LINK = re.compile(r"""href\s*=\s*["']([^"']+\.pdf)["']""", re.IGNORECASE)
BREAK = re.compile(r"<(?:br|/?p|/?div|/?li|/?tr)\b[^>]*>", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


def _text(content: str | None) -> str:
    if not content:
        return ""

    lines = html.unescape(TAG.sub("", BREAK.sub("\n", content))).splitlines()

    return "\n".join(line.strip() for line in lines if line.strip())


def attachment_links(row: tables.EGXNews) -> list[str]:
    links = [
        href if href.startswith("http") else f"{egx_settings.download_base_url}{href}"
        for content in (row.content, row.content_ar)
        for href in PDF_LINK.findall(content or "")
    ]

    return list(dict.fromkeys(links))


def announcement(row: tables.EGXNews) -> str:
    timezone = ZoneInfo(settings.egx_market.timezone)
    published = row.date_stamp.astimezone(timezone) if row.date_stamp else None
    parts = [
        ("Heading", row.heading),
        ("Heading, in Arabic", row.heading_ar),
        ("Company", row.company_name),
        ("Company, in Arabic", row.company_name_ar),
        ("Section", row.section),
        ("Published, Cairo time", published and f"{published:%Y-%m-%d %H:%M}"),
        ("Text", _text(row.content)),
        ("Text, in Arabic", _text(row.content_ar)),
    ]

    return "\n\n".join(f"{label}:\n{value}" for label, value in parts if value)


def _until_quota_midnight(now: datetime) -> int:
    local = now.astimezone(ZoneInfo(settings.gemini.quota_timezone))
    midnight = datetime.combine(
        local.date() + timedelta(days=1),
        time(),
        local.tzinfo,
    )

    return max(1, math.ceil((midnight - local).total_seconds()))


def _quota_day(now: datetime) -> str:
    return now.astimezone(ZoneInfo(settings.gemini.quota_timezone)).date().isoformat()


async def _paused(redis: Redis) -> int | None:
    try:
        left = await redis.ttl(CacheKeys.GEMINI_PAUSED)
    except RedisError:
        return None

    return left if left > 0 else None


async def _pause(redis: Redis, exc: SummarizerBusyError, *, now: datetime) -> int:
    gemini = settings.gemini
    try:
        streak = int(await redis.incr(CacheKeys.GEMINI_BUSY_STREAK))

        await redis.expire(CacheKeys.GEMINI_BUSY_STREAK, 24 * 60 * 60)
    except RedisError:
        streak = 1

    waited = max(exc.retry_after_seconds or 0, gemini.busy_pause_seconds)
    backoff = min(waited * 2 ** (streak - 1), gemini.longest_pause_seconds)
    seconds = _until_quota_midnight(now) if exc.daily else math.ceil(backoff)

    try:
        await redis.set(CacheKeys.GEMINI_PAUSED, exc.message, ex=seconds)
    except RedisError:
        logger.warning(
            "[News Summaries] Could Not Pause - Redis Is Unavailable",
        )

    return seconds


async def _not_busy(redis: Redis) -> None:
    try:
        await redis.delete(CacheKeys.GEMINI_BUSY_STREAK)
    except RedisError:
        return


RUN_LOCK_SECONDS = 30 * 60


async def _start_run(redis: Redis, token: str) -> bool:
    try:
        return bool(
            await redis.set(
                CacheKeys.GEMINI_RUNNING,
                token,
                nx=True,
                ex=RUN_LOCK_SECONDS,
            ),
        )
    except RedisError:
        return True


async def _end_run(redis: Redis, token: str) -> None:
    try:
        if await redis.get(CacheKeys.GEMINI_RUNNING) in (token, token.encode()):
            await redis.delete(CacheKeys.GEMINI_RUNNING)
    except RedisError:
        return


async def _requests_today(redis: Redis, *, now: datetime, add: int = 0) -> int:
    key = CacheKeys.GEMINI_REQUESTS.format(day=_quota_day(now))

    try:
        if not add:
            return int(await redis.get(key) or 0)

        count = await redis.incrby(key, add)

        await redis.expire(key, _until_quota_midnight(now) + 24 * 60 * 60)
    except RedisError:
        return 0

    return int(count)


async def summarize_news(
    gemini: GeminiService | None,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    now: datetime,
    limit: int,
    pause_seconds: float = 0,
) -> dict[str, int] | None:
    if gemini is None:
        logger.info("[News Summaries] Skipped - No Gemini Key")

        return None

    if (left := await _paused(redis)) is not None:
        logger.info("[News Summaries] Skipped - Gemini Is Paused", seconds_left=left)

        return None

    token = uuid4().hex
    if not await _start_run(redis, token):
        logger.info("[News Summaries] Skipped - Another Run Is Going")

        return None
    try:
        return await _summarize(
            gemini,
            session_factory,
            redis,
            now=now,
            limit=limit,
            pause_seconds=pause_seconds,
        )
    finally:
        await _end_run(redis, token)


async def _summarize(
    gemini: GeminiService,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    now: datetime,
    limit: int,
    pause_seconds: float,
) -> dict[str, int]:
    daily_limit = settings.gemini.requests_per_day

    news = settings.egx_news
    async with session_factory() as session:
        rows = await egx_repositories.get_news_to_summarize(
            session,
            max_attempts=news.summarize_max_attempts,
            limit=limit,
        )

    done = failed = 0
    busy = False
    for index, row in enumerate(rows):
        if daily_limit and await _requests_today(redis, now=now) >= daily_limit:
            logger.info(
                "[News Summaries] Stopped - Daily Limit",
                limit=daily_limit,
            )

            break
        if index:
            await asyncio.sleep(pause_seconds)

        try:
            await _requests_today(redis, now=now, add=1)
            draft = await gemini.summarize_news(
                announcement(row),
                attachments=attachment_links(row),
            )
        except SummarizerBusyError as exc:
            busy = True

            logger.warning(
                "[News Summaries] Stopped - Gemini Is Busy",
                code=row.code,
                error=exc.message,
                daily=exc.daily,
                paused_seconds=await _pause(redis, exc, now=now),
            )

            break
        except SummarizerError as exc:
            failed += 1

            logger.warning(
                "[News Summaries] Failed",
                code=row.code,
                error=exc.message,
            )

            async with session_factory() as session, session.begin():
                await egx_repositories.record_summary_failure(
                    session,
                    row.code,
                    exc.message,
                )

            continue

        done += 1
        await _not_busy(redis)
        async with session_factory() as session, session.begin():
            await egx_repositories.save_news_summary(
                session,
                row.code,
                summary=draft.summary,
                summary_ar=draft.summary_ar,
                key_points=draft.key_points,
                key_points_ar=draft.key_points_ar,
                model=gemini.model,
                read_attachments=draft.read_attachments,
            )

    counts = {
        "summarized": done,
        "failed": failed,
        "stopped_busy": int(busy),
    }

    logger.info(
        "[News Summaries] Done",
        **counts,
    )

    return counts
