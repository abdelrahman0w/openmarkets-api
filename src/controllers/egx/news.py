from redis.asyncio import Redis

from src.actions import cached_live_json
from src.exceptions import NotFoundError
from src.services import EGXService
from src.structs.models import Page
from src.structs.models.requests import EGXFinancialStatementsRequest
from src.structs.models.requests import EGXNewsDetailRequest
from src.structs.models.requests import EGXNewsSearchRequest
from src.structs.models.responses import EGXNewsItem


async def search_news(
    egx: EGXService,
    redis: Redis,
    request: EGXNewsSearchRequest,
) -> str:
    return await cached_live_json(
        redis,
        "news",
        lambda: egx.news_search(request),
        Page[EGXNewsItem],
        request,
    )


async def get_news_item(
    egx: EGXService,
    redis: Redis,
    request: EGXNewsDetailRequest,
) -> str:
    async def news_item() -> EGXNewsItem:
        item = await egx.news_detail(request)
        if item is None:
            raise NotFoundError(f"News item {request.id} was not found")

        return item

    return await cached_live_json(
        redis,
        "news-item",
        news_item,
        EGXNewsItem,
        request,
    )


async def get_financial_statements(
    egx: EGXService,
    redis: Redis,
    request: EGXFinancialStatementsRequest,
) -> str:
    return await cached_live_json(
        redis,
        "financial-statements",
        lambda: egx.financial_statements(request),
        Page[EGXNewsItem],
        request,
    )
