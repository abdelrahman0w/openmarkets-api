import argparse
from datetime import UTC
from datetime import datetime

from src.actions import egx as egx_actions
from src.jobs import Job
from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.services import EGXConnection
from src.services import GeminiConnection
from src.settings import settings
from src.structs.enums import EGXIndexName


# five years of daily closes, with a margin
DEFAULT_BACKFILL_DAYS = 1900
# slow enough for egx's firewall, which blocked 5 at once, and 2 a second apart
DEFAULT_BACKFILL_CONCURRENCY = 1
DEFAULT_BACKFILL_PAUSE_SECONDS = 3.0
# a page of index history as big as egx allows
INDEX_BACKFILL_PAGE_SIZE = 250
# five years of news, with a margin, a page is as big as egx allows
DEFAULT_NEWS_BACKFILL_DAYS = 1830
NEWS_BACKFILL_PAGE_SIZE = 250


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    return number


def _non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")

    return number


async def sync_stock_prices(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.sync_stock_prices(
        EGXConnection.get(),
        DatabaseSessions.get(),
        RedisConnection.get(),
        now=datetime.now(UTC),
        force=args.force,
    )


def sync_stock_prices_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="sync and store even while the market is closed",
    )


async def prune_stock_quotes(
    _: argparse.Namespace,
) -> object:
    return await egx_actions.prune_stock_quotes(
        DatabaseSessions.get(),
        now=datetime.now(UTC),
    )


async def backfill_stock_prices(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.backfill_stock_prices(
        EGXConnection.get(),
        DatabaseSessions.get(),
        days=args.days,
        isins=args.isin,
        missing_only=args.missing_only,
        concurrency=args.concurrency,
        pause_seconds=args.pause,
    )


def backfill_stock_prices_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_BACKFILL_DAYS,
        help="how many days back",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="only stocks without a price history yet",
    )
    parser.add_argument(
        "--isin",
        action="append",
        help="only this stock, can be repeated",
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=DEFAULT_BACKFILL_CONCURRENCY,
        help="how many stocks are asked for at once",
    )
    parser.add_argument(
        "--pause",
        type=_non_negative_float,
        default=DEFAULT_BACKFILL_PAUSE_SECONDS,
        help="seconds to wait after each request",
    )


async def sync_news(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.sync_news(
        EGXConnection.get(),
        DatabaseSessions.get(),
        RedisConnection.get(),
        now=datetime.now(UTC),
        force=args.force,
        delay_seconds=args.delay,
    )


def sync_news_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="sync now, even when it is not due",
    )
    parser.add_argument(
        "--delay",
        type=_non_negative_float,
        default=settings.egx_news.sync_delay_seconds,
        help="seconds to wait before asking egx, after the price sync",
    )


async def backfill_news(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.backfill_news(
        EGXConnection.get(),
        DatabaseSessions.get(),
        now=datetime.now(UTC),
        days=args.days,
        page_size=NEWS_BACKFILL_PAGE_SIZE,
        from_page=args.from_page,
        pause_seconds=args.pause,
    )


def backfill_news_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--days",
        type=_positive_int,
        default=DEFAULT_NEWS_BACKFILL_DAYS,
        help="how many days back",
    )
    parser.add_argument(
        "--from-page",
        type=_positive_int,
        default=1,
        help="the page to start from, to resume a backfill that stopped",
    )
    parser.add_argument(
        "--pause",
        type=_non_negative_float,
        default=DEFAULT_BACKFILL_PAUSE_SECONDS,
        help="seconds to wait after each page",
    )


async def sync_indices(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.sync_indices(
        EGXConnection.get(),
        DatabaseSessions.get(),
        RedisConnection.get(),
        now=datetime.now(UTC),
        force=args.force,
        delay_seconds=args.delay,
    )


def sync_indices_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="sync now, even when it is not due or the market is closed",
    )
    parser.add_argument(
        "--delay",
        type=_non_negative_float,
        default=settings.egx_indices.sync_delay_seconds,
        help="seconds to wait before asking egx, after the price and news syncs",
    )


async def backfill_indices(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.backfill_indices(
        EGXConnection.get(),
        DatabaseSessions.get(),
        indices=args.index,
        missing_only=args.missing_only,
        page_size=INDEX_BACKFILL_PAGE_SIZE,
        pause_seconds=args.pause,
    )


def backfill_indices_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--index",
        action="append",
        type=EGXIndexName,
        choices=list(EGXIndexName),
        help="only this index, by its egx code, can be repeated",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="only indices without a history yet",
    )
    parser.add_argument(
        "--pause",
        type=_non_negative_float,
        default=DEFAULT_BACKFILL_PAUSE_SECONDS,
        help="seconds to wait after each page",
    )


async def summarize_news(
    args: argparse.Namespace,
) -> object:
    return await egx_actions.summarize_news(
        GeminiConnection.get(),
        DatabaseSessions.get(),
        RedisConnection.get(),
        now=datetime.now(UTC),
        limit=args.limit,
        pause_seconds=args.pause,
    )


def summarize_news_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=settings.egx_news.summarize_batch_size,
        help="how many items to summarize at most, the newest first",
    )
    parser.add_argument(
        "--pause",
        type=_non_negative_float,
        default=settings.egx_news.summarize_pause_seconds,
        help="seconds to wait between items",
    )


JOBS: dict[str, Job] = {
    "sync_stock_prices": Job(
        run=sync_stock_prices,
        help="store a quote per stock while the market is open",
        arguments=sync_stock_prices_arguments,
        monitor_every_seconds=60,
    ),
    "prune_stock_quotes": Job(
        run=prune_stock_quotes,
        help="drop the quotes past the retention",
        monitor_every_seconds=24 * 60 * 60,
    ),
    "backfill_stock_prices": Job(
        run=backfill_stock_prices,
        help="store every stock's daily closes, fired by hand",
        arguments=backfill_stock_prices_arguments,
    ),
    "sync_news": Job(
        run=sync_news,
        help="store the latest news, when due, by the EGX_NEWS_SYNC_* minutes",
        arguments=sync_news_arguments,
        monitor_every_seconds=60,
    ),
    "sync_indices": Job(
        run=sync_indices,
        help="store every index's level, when due, by EGX_INDICES_SYNC_EVERY_MINUTES",
        arguments=sync_indices_arguments,
        monitor_every_seconds=60,
    ),
    "backfill_indices": Job(
        run=backfill_indices,
        help="store every index's daily history since its inception, fired by hand",
        arguments=backfill_indices_arguments,
    ),
    "summarize_news": Job(
        run=summarize_news,
        help="summarize the stored news gemini has not yet, off without GEMINI_API_KEY",
        arguments=summarize_news_arguments,
        monitor_every_seconds=5 * 60,
    ),
    "backfill_news": Job(
        run=backfill_news,
        help="store the news of the last 5 years, fired by hand",
        arguments=backfill_news_arguments,
    ),
}
