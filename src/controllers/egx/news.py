from datetime import datetime
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions import cached_live_json
from src.exceptions import NotFoundError
from src.exceptions import UnsupportedError
from src.repositories import egx as egx_repositories
from src.services import EGXService
from src.settings import settings
from src.structs.models import Page
from src.structs.models.requests import EGXFinancialStatementsRequest
from src.structs.models.requests import EGXNewsDetailRequest
from src.structs.models.requests import EGXStockNewsRequest
from src.structs.models.requests import EGXStoredNewsSearchRequest
from src.structs.models.responses import EGXNewsItem
from src.structs.models.responses import EGXNewsItemDetail
from src.utils import adapter


STOCK_NEWS_FALLBACK_DAYS = 365


async def _from_storage(session: AsyncSession) -> bool:
    return settings.egx_news.serve_from_storage and await egx_repositories.has_news(
        session,
    )


async def search_news(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
    request: EGXStoredNewsSearchRequest,
) -> str:
    if await _from_storage(session):
        return await cached_live_json(
            redis,
            "news-stored",
            lambda: egx_repositories.search_news(
                session,
                page=request.page_number,
                page_size=request.page_size,
                timezone=settings.egx_market.timezone,
                sec_ids=request.sec_ids,
                search_text=request.search_text,
                date_from=request.date_from,
                date_to=request.date_to,
                isin=request.isin,
                has_attachments=request.has_attachments,
            ),
            Page[EGXNewsItem],
            request,
        )

    if request.stored_only:
        raise UnsupportedError(
            "Filtering the news by company or attachments needs the stored news",
        )

    return await cached_live_json(
        redis,
        "news",
        lambda: egx.news_search(request.for_egx()),
        Page[EGXNewsItem],
        request,
        ttl_seconds=settings.redis.news_cache_seconds,
        fresh_seconds=settings.redis.news_fresh_seconds,
    )


async def get_news_item(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
    request: EGXNewsDetailRequest,
) -> str:
    if settings.egx_news.serve_from_storage and not request.market_session_news:
        stored = await egx_repositories.get_news_item(session, request.id)
        if stored is not None:
            detail = EGXNewsItemDetail.model_construct(
                **{name: getattr(stored, name) for name in EGXNewsItem.model_fields},
                summary=await egx_repositories.get_news_summary(session, request.id),
            )

            return adapter(EGXNewsItemDetail).dump_json(detail).decode()

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
        ttl_seconds=settings.redis.news_item_cache_seconds,
    )


async def get_stock_news(
    egx: EGXService,
    session: AsyncSession,
    redis: Redis,
    request: EGXStockNewsRequest,
    *,
    now: datetime,
) -> str:
    if await _from_storage(session):
        if await egx_repositories.get_stock_id(session, request.isin) is None:
            raise NotFoundError(f"Stock {request.isin} was not found")

        return await cached_live_json(
            redis,
            "stock-news",
            lambda: egx_repositories.search_news(
                session,
                page=request.page_number,
                page_size=request.page_size,
                timezone=settings.egx_market.timezone,
                isin=request.isin,
            ),
            Page[EGXNewsItem],
            request,
        )

    stock = await egx_repositories.get_stock(session, request.isin)
    if stock is None or not stock.reuters:
        raise NotFoundError(f"Stock {request.isin} was not found")

    return await search_news(
        egx,
        session,
        redis,
        EGXStoredNewsSearchRequest(
            search_text=stock.reuters,
            date_from=(now - timedelta(days=STOCK_NEWS_FALLBACK_DAYS)).date(),
            page_number=request.page_number,
            page_size=request.page_size,
        ),
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
        ttl_seconds=settings.redis.news_cache_seconds,
        fresh_seconds=settings.redis.news_fresh_seconds,
    )
