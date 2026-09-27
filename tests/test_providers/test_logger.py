import json
import logging
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from src.providers import logger
from src.providers import setup_logging


REQUEST_LOG = "[API Access Request]"


@pytest.fixture
def json_lines(
    capsys: pytest.CaptureFixture[str],
):
    setup_logging(level="DEBUG", json_logs=True)

    def read() -> list[dict]:
        return [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    yield read

    setup_logging(level="WARNING", json_logs=True)


def test_extras_are_fields_and_the_message_is_left_alone(json_lines) -> None:
    logger.info("braces {stay} as they are", isin="EGS1", count=3)

    (line,) = json_lines()
    assert line["message"] == "braces {stay} as they are"
    assert line["isin"] == "EGS1"
    assert line["count"] == 3
    assert line["function"] == "test_extras_are_fields_and_the_message_is_left_alone"


def test_contextualized_extras_are_on_every_line(json_lines) -> None:
    with logger.contextualize(correlation_id="abc-123"):
        logger.info("first")
        logger.warning("second")

    assert [line["correlation_id"] for line in json_lines()] == ["abc-123", "abc-123"]


def test_exceptions_are_attached(json_lines) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed", isin="EGS1")

    (line,) = json_lines()
    assert line["level"] == "ERROR"
    assert "ValueError: boom" in line["exception"]


async def test_a_request_is_logged_with_its_context(
    json_lines,
    client: AsyncClient,
    egx: AsyncMock,
) -> None:
    egx.gold_market_watch.return_value = []

    await client.get(
        "/egx/market/gold",
        headers={"cf-connecting-ip": "41.33.10.7", "x-correlation-id": "abc-123"},
    )

    (line,) = [line for line in json_lines() if line["message"].startswith(REQUEST_LOG)]
    assert line["level"] == "INFO"
    assert line["method"] == "GET"
    assert line["path"] == "/egx/market/gold"
    assert line["status_code"] == 200
    assert line["duration_ms"] >= 0
    assert line["correlation_id"] == "abc-123"
    assert line["cf_connecting_ip"] == "41.33.10.7"
    assert line["client_ip"] == "41.33.10.7"


async def test_health_probes_are_logged_at_debug(
    json_lines, client: AsyncClient
) -> None:
    await client.get("/health/live")

    (line,) = [line for line in json_lines() if line["message"].startswith(REQUEST_LOG)]
    assert line["level"] == "DEBUG"
    assert line["path"] == "/health/live"


async def test_a_crashed_request_is_logged_as_a_500(
    json_lines,
    client: AsyncClient,
    egx: AsyncMock,
) -> None:
    egx.gold_market_watch.side_effect = RuntimeError("boom")

    # the test transport re-raises what the app did not handle
    with pytest.raises(RuntimeError):
        await client.get("/egx/market/gold")

    (line,) = [line for line in json_lines() if line["message"].startswith(REQUEST_LOG)]
    assert line["level"] == "ERROR"
    assert line["status_code"] == 500


def test_uvicorn_access_logs_are_off() -> None:
    setup_logging(level="WARNING", json_logs=True)

    # uvicorn only writes access logs when this logger reaches a handler
    assert not logging.getLogger("uvicorn.access").hasHandlers()
    assert logging.getLogger("uvicorn.error").hasHandlers()
