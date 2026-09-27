from typing import Annotated

from fastapi import APIRouter
from fastapi import Query

from src.controllers.egx import market as market_controller
from src.dependencies import EGXServiceDep
from src.dependencies import NowDep
from src.dependencies import RedisDep
from src.routes.responses import JSONText
from src.structs.models.requests import EGXDerivativesWatchRequest
from src.structs.models.requests import EGXPriceVolumePointsRequest
from src.structs.models.requests import EGXStockMarketWatchRequest


router = APIRouter(prefix="/market")


@router.get("/status")
async def get_market_status(
    egx: EGXServiceDep,
    redis: RedisDep,
    now: NowDep,
) -> JSONText:
    return JSONText(
        await market_controller.get_market_status(
            egx,
            redis,
            now=now,
        )
    )


@router.get("/stocks")
async def get_stock_market_watch(
    egx: EGXServiceDep,
    redis: RedisDep,
    request: Annotated[EGXStockMarketWatchRequest, Query()],
) -> JSONText:
    return JSONText(
        await market_controller.get_stock_market_watch(
            egx,
            redis,
            request,
        ),
    )


@router.get("/gold")
async def get_gold_market_watch(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await market_controller.get_gold_market_watch(
            egx,
            redis,
        )
    )


@router.get("/silver")
async def get_silver_market_watch(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await market_controller.get_silver_market_watch(
            egx,
            redis,
        )
    )


@router.get("/derivatives")
async def get_derivatives_watch(
    egx: EGXServiceDep,
    redis: RedisDep,
    request: Annotated[EGXDerivativesWatchRequest, Query()],
) -> JSONText:
    return JSONText(
        await market_controller.get_derivatives_watch(
            egx,
            redis,
            request,
        )
    )


@router.get("/securities/{isin}/price-volume-points")
async def get_price_volume_points(
    egx: EGXServiceDep,
    redis: RedisDep,
    isin: str,
    days: Annotated[int, Query(ge=30)] = 30,
) -> JSONText:
    return JSONText(
        await market_controller.get_price_volume_points(
            egx,
            redis,
            EGXPriceVolumePointsRequest(isin=isin, days=days),
        ),
    )


@router.get("/summaries")
async def get_market_summaries(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await market_controller.get_market_summaries(
            egx,
            redis,
        )
    )


@router.get("/indicators")
async def get_market_indicators(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await market_controller.get_market_indicators(
            egx,
            redis,
        )
    )
