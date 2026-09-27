import contextlib
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from src.middlewares import logs_contextualizer
from src.structs.models.responses import EGXMetalQuote


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/redoc",
        "/openapi.json",
    ],
)
async def test_api_docs_are_not_served(
    client: AsyncClient,
    path: str,
) -> None:
    response = await client.get(path)

    assert response.status_code == 404


async def test_large_responses_are_compressed(
    client: AsyncClient,
    egx: AsyncMock,
) -> None:
    egx.gold_market_watch.return_value = [
        EGXMetalQuote(brand_name=f"Brand {n}") for n in range(50)
    ]

    response = await client.get(
        "/egx/market/gold",
        headers={"accept-encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert len(response.json()) == 50


async def test_correlation_id_is_echoed(
    client: AsyncClient,
    egx: AsyncMock,
) -> None:
    egx.gold_market_watch.return_value = []

    response = await client.get(
        "/egx/market/gold",
        headers={"x-correlation-id": "abc-123"},
    )

    assert response.headers["x-correlation-id"] == "abc-123"


async def test_correlation_id_is_generated(
    client: AsyncClient,
    egx: AsyncMock,
) -> None:
    egx.gold_market_watch.return_value = []

    response = await client.get("/egx/market/gold")

    assert len(response.headers["x-correlation-id"]) == 36


async def test_every_client_ip_is_logged(
    client: AsyncClient,
    egx: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def contextualize(
        **extra: str,
    ) -> contextlib.AbstractContextManager[None]:
        captured.update(extra)
        return contextlib.nullcontext()

    monkeypatch.setattr(
        logs_contextualizer.logger,
        "contextualize",
        contextualize,
    )
    egx.gold_market_watch.return_value = []

    await client.get(
        "/egx/market/gold",
        headers={
            "cf-connecting-ip": "41.33.10.7",
            "x-real-ip": "10.0.1.5",
            "x-forwarded-for": "41.33.10.7, 10.0.1.5",
        },
    )

    assert captured["cf_connecting_ip"] == "41.33.10.7"
    assert captured["real_ip"] == "10.0.1.5"
    assert captured["forwarded_for"] == "41.33.10.7, 10.0.1.5"
    assert captured["client_ip"] == "41.33.10.7"
