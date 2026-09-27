import json
from collections.abc import Awaitable

import httpx
from openmarkets.exchanges.egx.client import EGXClient
from openmarkets.utils.http_session import HTTPConfig
from pydantic import ValidationError

from src.exceptions import ExchangeError
from src.exceptions import ExchangeTimeoutError
from src.exceptions import ExchangeUnavailableError
from src.settings import settings
from src.structs.models import Page
from src.structs.models.requests import EGXDerivativesWatchRequest
from src.structs.models.requests import EGXFinancialStatementsRequest
from src.structs.models.requests import EGXNewsDetailRequest
from src.structs.models.requests import EGXNewsSearchRequest
from src.structs.models.requests import EGXPriceVolumePointsRequest
from src.structs.models.requests import EGXStockMarketWatchRequest
from src.structs.models.responses import EGXDerivativeWatchRow
from src.structs.models.responses import EGXMarketIndicator
from src.structs.models.responses import EGXMarketStatus
from src.structs.models.responses import EGXMarketSummaries
from src.structs.models.responses import EGXMetalQuote
from src.structs.models.responses import EGXMutualFund
from src.structs.models.responses import EGXNewsItem
from src.structs.models.responses import EGXPriceVolumePoint
from src.structs.models.responses import EGXStockMarketWatchRow
from src.structs.models.responses import EGXTreasuryBond
from src.utils import Singleton


MAX_PAGE_SIZE = 250


async def _call[T](request: Awaitable[T]) -> T:
    try:
        return await request
    except httpx.TimeoutException as exc:
        raise ExchangeTimeoutError("EGX took too long to respond") from exc
    except httpx.HTTPStatusError as exc:
        raise ExchangeError(
            f"EGX responded with status {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise ExchangeUnavailableError("EGX could not be reached") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ExchangeError("EGX returned an unexpected response") from exc


def _require[T](data: T | None) -> T:
    if data is None:
        raise ExchangeError("EGX returned no data")

    return data


def _page[T](items: list[T] | None, counters: object) -> Page[T]:
    return Page[T](
        items=items or [],
        page=getattr(counters, "page_number", None),
        page_size=getattr(counters, "page_size", None),
        total_count=getattr(counters, "total_count", None),
        total_pages=getattr(counters, "total_pages", None),
    )


class EGXService:
    def __init__(
        self,
        client: EGXClient | None = None,
    ) -> None:
        self._client = client or EGXClient()

    async def close(self) -> None:
        await self._client.close()

    async def market_status(self) -> EGXMarketStatus:
        return _require((await _call(self._client.market_status())).data)

    async def stock_market_watch(
        self,
        request: EGXStockMarketWatchRequest,
    ) -> Page[EGXStockMarketWatchRow]:
        page = _require((await _call(self._client.stock_market_watch(request))).data)

        return _page(page.data, page)

    async def stock_board(self) -> list[EGXStockMarketWatchRow]:
        rows: list[EGXStockMarketWatchRow] = []
        page = 1

        while True:
            result = await self.stock_market_watch(
                EGXStockMarketWatchRequest(page=page, page_size=MAX_PAGE_SIZE),
            )
            rows.extend(result.items)

            if page >= (result.total_pages or 1):
                return rows

            page += 1

    async def gold_market_watch(self) -> list[EGXMetalQuote]:
        return (await _call(self._client.gold_market_watch())).data or []

    async def silver_market_watch(self) -> list[EGXMetalQuote]:
        return (await _call(self._client.silver_market_watch())).data or []

    async def derivatives_watch(
        self,
        request: EGXDerivativesWatchRequest,
    ) -> Page[EGXDerivativeWatchRow]:
        page = _require((await _call(self._client.derivatives_watch(request))).data)

        return _page(page.data, page)

    async def price_volume_points(
        self,
        request: EGXPriceVolumePointsRequest,
    ) -> list[EGXPriceVolumePoint]:
        return (await _call(self._client.price_volume_points(request))).data or []

    async def market_summaries(self) -> EGXMarketSummaries:
        return _require((await _call(self._client.market_summaries())).data)

    async def market_indicators(self) -> list[EGXMarketIndicator]:
        return (await _call(self._client.market_indicators())).data or []

    async def treasury_bonds(self) -> list[EGXTreasuryBond]:
        return (await _call(self._client.treasury_bonds())).data or []

    async def mutual_funds(self) -> list[EGXMutualFund]:
        return (await _call(self._client.mutual_funds())).data or []

    async def news_search(
        self,
        request: EGXNewsSearchRequest,
    ) -> Page[EGXNewsItem]:
        response = await _call(self._client.news_search(request))

        return _page(response.data, response)

    async def news_detail(
        self,
        request: EGXNewsDetailRequest,
    ) -> EGXNewsItem | None:
        response = await _call(self._client.news_detail(request))

        return next(iter(response.data or []), None)

    async def financial_statements(
        self,
        request: EGXFinancialStatementsRequest,
    ) -> Page[EGXNewsItem]:
        response = await _call(self._client.financial_statements(request))

        return _page(response.data, response)


class EGXConnection(Singleton[EGXService]):
    @classmethod
    def create(cls) -> EGXService:
        timeout = settings.egx_market.request_timeout_seconds

        return EGXService(
            EGXClient(
                http_config=HTTPConfig(
                    timeout=timeout,
                    connect_timeout=min(timeout, 5.0),
                ),
            ),
        )

    @classmethod
    async def dispose(cls, instance: EGXService) -> None:
        await instance.close()
