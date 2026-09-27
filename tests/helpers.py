from datetime import date
from datetime import datetime
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import Text
from sqlalchemy import literal_column
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.settings import settings
from src.structs import tables
from src.structs.models.responses import EGXPriceVolumePoint
from src.structs.models.responses import EGXStockMarketWatchRow


COMI = "EGS60121C018"
HRHO = "EGS69101C011"


def override_settings(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    section: str,
    **values: Any,
) -> None:
    monkeypatch.setattr(
        module,
        "settings",
        settings.model_copy(
            update={section: getattr(settings, section).model_copy(update=values)},
        ),
    )


def make_row(
    **overrides: Any,
) -> EGXStockMarketWatchRow:
    fields: dict[str, Any] = {
        "isin": COMI,
        "reuters": "COMI.CA",
        "name": "Commercial International Bank-Egypt (CIB)",
        "name_ar": "البنك التجاري الدولي",
        "sec_id": 1,
        "sector": "Banks",
        "sector_ar": "بنوك",
        "market_code": "NOPL",
        "symbol_type": "C",
        "last_price": 128.1,
        "open_price": 127.0,
        "close_price": 128.1,
        "prev_close": 127.5,
        "high": 129.0,
        "low": 126.9,
        "change_percent": 0.47,
        "value": 700_000_000.25,
        "volume": 5_462_562,
        "trades": 3_120,
        "market_cap": 390_000_000_000.5,
        "net_profit": 55_000_000_000.0,
        "last_trade_date": date(2026, 9, 24),
        "write_time": datetime.fromisoformat("2026-09-24T09:00:00+00:00"),
        "currency": "Egyptian Pound",
        "currency_short": "L.E",
        "funds_code": 1,
        "intraday": "Y",
        "with_history": "N",
        "egx30_cap": "Y",
        "shariah": None,
    }

    return EGXStockMarketWatchRow(**(fields | overrides))


def make_point(
    trade_date: date,
    close_price: float,
) -> EGXPriceVolumePoint:
    return EGXPriceVolumePoint(
        isin=COMI,
        trade_date=trade_date,
        close_price=close_price,
        trade_volume=1_000,
    )


async def row_versions(
    session: AsyncSession,
    table: type[tables.Base],
) -> list[str]:
    ctid = literal_column("ctid")

    return list(
        await session.scalars(select(ctid.cast(Text)).select_from(table).order_by(ctid))
    )
