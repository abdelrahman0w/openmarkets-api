from typing import Annotated

from fastapi import APIRouter
from fastapi import Query

from src.controllers.egx import news as news_controller
from src.dependencies import EGXServiceDep
from src.dependencies import RedisDep
from src.routes.responses import JSONText
from src.structs.models.requests import EGXFinancialStatementsRequest
from src.structs.models.requests import EGXNewsDetailRequest
from src.structs.models.requests import EGXNewsSearchRequest


router = APIRouter(prefix="/news")


@router.get("")
async def search_news(
    egx: EGXServiceDep,
    redis: RedisDep,
    request: Annotated[EGXNewsSearchRequest, Query()],
) -> JSONText:
    return JSONText(
        await news_controller.search_news(
            egx,
            redis,
            request,
        )
    )


@router.get("/financial-statements")
async def get_financial_statements(
    egx: EGXServiceDep,
    redis: RedisDep,
    request: Annotated[EGXFinancialStatementsRequest, Query()],
) -> JSONText:
    return JSONText(
        await news_controller.get_financial_statements(
            egx,
            redis,
            request,
        ),
    )


@router.get("/{news_id}")
async def get_news_item(
    egx: EGXServiceDep,
    redis: RedisDep,
    news_id: int,
    *,
    market_session_news: Annotated[bool, Query()] = False,
) -> JSONText:
    return JSONText(
        await news_controller.get_news_item(
            egx,
            redis,
            EGXNewsDetailRequest(
                id=news_id,
                market_session_news=market_session_news,
            ),
        ),
    )
