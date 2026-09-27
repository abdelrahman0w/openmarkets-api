import argparse
from contextlib import nullcontext

import pytest

from src.jobs import main as jobs
from src.jobs.base import Job
from src.providers import monitor_job


ARGS = argparse.Namespace()


@pytest.fixture
def monitored(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def fake_monitor(
        name: str,
        every_seconds: int,
    ) -> nullcontext[None]:
        calls.append((name, every_seconds))

        return nullcontext()

    monkeypatch.setattr(jobs, "monitor_job", fake_monitor)

    return calls


async def succeeds(
    _: argparse.Namespace,
) -> None:
    return None


async def fails(
    _: argparse.Namespace,
) -> None:
    raise RuntimeError("boom")


def register(
    monkeypatch: pytest.MonkeyPatch,
    job: Job,
) -> None:
    monkeypatch.setitem(jobs.JOBS, "test_job", job)


def messages(
    lines: list[dict],
) -> dict[str, dict]:
    return {line["message"]: line for line in lines}


async def test_a_run_is_logged_with_its_duration(
    json_lines,
    monitored: list[tuple[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(monkeypatch, Job(run=succeeds, help="a test job"))

    await jobs.run_job("test_job", ARGS)

    lines = messages(json_lines())

    assert lines["[Jobs] Job Started"]["job"] == "test_job"
    assert lines["[Jobs] Job Finished"]["level"] == "INFO"
    assert lines["[Jobs] Job Finished"]["duration_ms"] >= 0
    assert monitored == []


async def test_a_failed_run_is_logged_and_raised(
    json_lines,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(monkeypatch, Job(run=fails, help="a test job"))

    with pytest.raises(RuntimeError):
        await jobs.run_job("test_job", ARGS)

    failed = messages(json_lines())["[Jobs] Job Failed"]

    assert failed["level"] == "ERROR"
    assert "RuntimeError: boom" in failed["exception"]


async def test_a_job_with_an_interval_is_monitored(
    monitored: list[tuple[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(
        monkeypatch,
        Job(
            run=succeeds,
            help="a test job",
            monitor_every_seconds=60,
        ),
    )

    await jobs.run_job("test_job", ARGS)

    assert monitored == [("test_job", 60)]


def test_each_job_takes_only_its_own_flags() -> None:
    args = jobs.parse_args(
        [
            "backfill_stock_prices",
            "--days",
            "30",
            "--missing-only",
        ],
    )

    assert (args.job, args.days, args.missing_only) == (
        "backfill_stock_prices",
        30,
        True,
    )

    with pytest.raises(SystemExit):
        jobs.parse_args(["prune_stock_quotes", "--days", "30"])


def test_a_job_is_required() -> None:
    with pytest.raises(SystemExit):
        jobs.parse_args([])


def test_every_job_has_a_subcommand() -> None:
    for name in jobs.JOBS:
        assert jobs.parse_args([name]).job == name


@pytest.mark.parametrize(
    ("every_seconds", "schedule"),
    [
        (60, {"type": "interval", "value": 1, "unit": "minute"}),
        (300, {"type": "interval", "value": 5, "unit": "minute"}),
        (30, {"type": "interval", "value": 1, "unit": "minute"}),
        (24 * 60 * 60, {"type": "interval", "value": 1, "unit": "day"}),
    ],
)
def test_the_monitor_follows_the_interval(
    every_seconds: int,
    schedule: dict,
) -> None:
    monitor = monitor_job("sync_stock_prices", every_seconds)

    assert monitor.monitor_slug == "jobs-sync-stock-prices"
    assert monitor.monitor_config["schedule"] == schedule
