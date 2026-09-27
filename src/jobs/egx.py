import argparse
from datetime import UTC
from datetime import datetime

from src.actions import egx as egx_actions
from src.jobs import Job
from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.services import EGXConnection


# five years of daily closes, with a margin
DEFAULT_BACKFILL_DAYS = 1900
# slow enough for egx's firewall, which blocked 5 at once, and 2 a second apart
DEFAULT_BACKFILL_CONCURRENCY = 1
DEFAULT_BACKFILL_PAUSE_SECONDS = 3.0


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
}
