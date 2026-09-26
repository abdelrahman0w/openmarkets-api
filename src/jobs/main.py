import argparse
import asyncio
import time
from collections.abc import Awaitable
from collections.abc import Callable
from contextlib import nullcontext
from contextlib import suppress

import uvloop

from src.providers import DatabaseConnection
from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.providers import enable_async_error_tracking
from src.providers import logger
from src.providers import monitor_job
from src.providers import setup_error_tracking
from src.providers import setup_logging
from src.settings import settings
from src.utils import connect_singletons


DEFAULT_BACKFILL_DAYS = 1900

SINGLETONS = (
    DatabaseConnection,
    DatabaseSessions,
    RedisConnection,
)


Job = Callable[[argparse.Namespace], Awaitable[object]]


JOBS: dict[str, Job] = {}

SCHEDULE: dict[str, int] = {}


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jobs")
    parser.add_argument("job", choices=["schedule", *sorted(JOBS)])

    return parser.parse_args(argv)


async def run_job(
    name: str,
    args: argparse.Namespace,
    *,
    every_seconds: int | None = None,
) -> None:
    monitor = monitor_job(name, every_seconds) if every_seconds else nullcontext()
    started = time.perf_counter()

    with logger.contextualize(job=name), monitor:
        logger.info(
            "[Jobs] Job Started",
            job_name=name,
        )

        try:
            await JOBS[name](args)
        except Exception:
            logger.exception(
                "[Jobs] Job Failed",
                job_name=name,
                duration_ms=_elapsed_ms(started),
            )
            raise

        logger.info(
            "[Jobs] Job Finished",
            job_name=name,
            duration_ms=_elapsed_ms(started),
        )


async def run_every(
    name: str,
    seconds: int,
    args: argparse.Namespace,
) -> None:
    while True:
        with suppress(Exception):
            await run_job(
                name,
                args,
                every_seconds=seconds,
            )

        await asyncio.sleep(seconds - time.time() % seconds)


async def run(
    args: argparse.Namespace,
) -> None:
    enable_async_error_tracking()

    async with connect_singletons(*SINGLETONS):
        if args.job != "schedule":
            await run_job(args.job, args)

            return

        async with asyncio.TaskGroup() as group:
            for name, seconds in SCHEDULE.items():
                group.create_task(
                    run_every(name, seconds, args),
                )


def main(
    argv: list[str] | None = None,
) -> None:
    setup_logging(
        level=settings.app.log_level,
        json_logs=settings.app.log_json,
    )
    setup_error_tracking(
        settings.error_tracking,
        settings.app,
    )

    uvloop.run(run(parse_args(argv)))


if __name__ == "__main__":
    main()
