from fastapi import APIRouter

from src.controllers.egx import indices as indices_controller
from src.dependencies import DBSessionDep
from src.dependencies import EGXServiceDep
from src.dependencies import RedisDep
from src.routes.responses import JSONText
from src.structs.enums import HistoryPeriods
from src.structs.enums import PerformancePeriods


router = APIRouter(prefix="/indices")


@router.get("")
async def list_indices(
    session: DBSessionDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await indices_controller.list_indices(
            session,
            redis,
        ),
    )


@router.get("/performance")
async def get_indices_performance(
    session: DBSessionDep,
    redis: RedisDep,
    period: PerformancePeriods = PerformancePeriods.ONE_MONTH,
) -> JSONText:
    return JSONText(
        await indices_controller.get_indices_performance(
            session,
            redis,
            period=period,
        ),
    )


@router.get("/{index}/history")
async def get_index_history(
    session: DBSessionDep,
    redis: RedisDep,
    index: str,
    period: HistoryPeriods = HistoryPeriods.ONE_MONTH,
) -> JSONText:
    return JSONText(
        await indices_controller.get_index_history(
            session,
            redis,
            code=index,
            period=period,
        ),
    )


@router.get("/{index}/summary")
async def get_index_summary(
    egx: EGXServiceDep,
    redis: RedisDep,
    index: str,
) -> JSONText:
    return JSONText(
        await indices_controller.get_index_summary(
            egx,
            redis,
            code=index,
        ),
    )


@router.get("/{index}/weights")
async def get_index_weights(
    egx: EGXServiceDep,
    redis: RedisDep,
    index: str,
) -> JSONText:
    return JSONText(
        await indices_controller.get_index_weights(
            egx,
            redis,
            code=index,
        ),
    )
