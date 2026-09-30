from fastapi import APIRouter

from src.routes.egx import indices
from src.routes.egx import instruments
from src.routes.egx import market
from src.routes.egx import news
from src.routes.egx import stocks


router = APIRouter(prefix="/egx")

router.include_router(market.router)
router.include_router(instruments.router)
router.include_router(indices.router)
router.include_router(news.router)
router.include_router(stocks.router)
