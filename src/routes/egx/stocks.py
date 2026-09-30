from typing import Annotated

from fastapi import APIRouter
from fastapi import Query

from src.controllers.egx import news as news_controller
from src.controllers.egx import stocks as stocks_controller
from src.dependencies import DBSessionDep
from src.dependencies import EGXServiceDep
from src.dependencies import NowDep
from src.dependencies import RedisDep
from src.routes.responses import JSONText
from src.structs.enums import HistoryPeriods
from src.structs.enums import PerformancePeriods
from src.structs.models.requests import EGXStockNewsRequest


router = APIRouter(prefix="/stocks")


@router.get("")
async def list_stocks(
    egx: EGXServiceDep,
    session: DBSessionDep,
    redis: RedisDep,
    now: NowDep,
) -> JSONText:
    return JSONText(
        await stocks_controller.list_stocks(
            egx,
            session,
            redis,
            now=now,
        )
    )


@router.get("/performance")
async def get_stocks_performance(
    session: DBSessionDep,
    redis: RedisDep,
    period: PerformancePeriods = PerformancePeriods.ONE_MONTH,
) -> JSONText:
    return JSONText(
        await stocks_controller.get_stocks_performance(
            session,
            redis,
            period=period,
        ),
    )


@router.get("/{isin}")
async def get_stock(
    egx: EGXServiceDep,
    session: DBSessionDep,
    redis: RedisDep,
    now: NowDep,
    isin: str,
) -> JSONText:
    return JSONText(
        await stocks_controller.get_stock(
            egx,
            session,
            redis,
            isin=isin,
            now=now,
        ),
    )


@router.get("/{isin}/history")
async def get_stock_history(
    session: DBSessionDep,
    redis: RedisDep,
    isin: str,
    period: HistoryPeriods = HistoryPeriods.ONE_MONTH,
) -> JSONText:
    return JSONText(
        await stocks_controller.get_stock_history(
            session,
            redis,
            isin=isin,
            period=period,
        ),
    )


@router.get("/{isin}/news")
async def get_stock_news(
    egx: EGXServiceDep,
    session: DBSessionDep,
    redis: RedisDep,
    now: NowDep,
    isin: str,
    page_number: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=250)] = 20,
) -> JSONText:
    return JSONText(
        await news_controller.get_stock_news(
            egx,
            session,
            redis,
            EGXStockNewsRequest(
                isin=isin, page_number=page_number, page_size=page_size
            ),
            now=now,
        ),
    )
