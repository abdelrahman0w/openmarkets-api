from fastapi import APIRouter

from src.controllers.egx import instruments as instruments_controller
from src.dependencies import EGXServiceDep
from src.dependencies import RedisDep
from src.routes.responses import JSONText


router = APIRouter(prefix="/instruments")


@router.get("/treasury-bonds")
async def get_treasury_bonds(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await instruments_controller.get_treasury_bonds(
            egx,
            redis,
        )
    )


@router.get("/mutual-funds")
async def get_mutual_funds(
    egx: EGXServiceDep,
    redis: RedisDep,
) -> JSONText:
    return JSONText(
        await instruments_controller.get_mutual_funds(
            egx,
            redis,
        )
    )
