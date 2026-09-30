from datetime import date
from datetime import datetime

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from src.structs.enums import EGXSymbolTypes
from src.structs.enums import HistoryPeriods
from src.structs.enums import PerformancePeriods
from src.structs.enums import PriceIntervals

from .market import EGXStockMarketWatchRow


INDEX_FIELDS = (
    "case30",
    "cwpc",
    "djeg20",
    "egx20",
    "egx30_cap",
    "egx50",
    "egx70",
    "egx100",
    "egx_sp",
    "shariah",
    "tamayuz",
    "volatility",
)


class EGXStockSector(BaseModel):
    egx_id: int
    name: str | None = None
    name_ar: str | None = None


class EGXStockCurrency(BaseModel):
    code: str
    code_ar: str | None = None
    name: str | None = None
    name_ar: str | None = None


class EGXStockQuote(BaseModel):
    quoted_at: datetime
    trade_date: date | None = None
    last_price: float | None = None
    open_price: float | None = None
    close_price: float | None = None
    prev_close: float | None = None
    high: float | None = None
    low: float | None = None
    change_percent: float | None = None
    value: float | None = None
    volume: int | None = None
    trades: int | None = None
    market_cap: float | None = None
    net_profit: float | None = None


class EGXStock(BaseModel):
    isin: str
    reuters: str | None = None
    name: str | None = None
    name_ar: str | None = None
    market_code: str | None = None
    sector: EGXStockSector | None = None
    currency: EGXStockCurrency | None = None
    funds_code: int | None = None
    is_intraday: bool = False
    has_history: bool = False
    indices: list[str] = Field(default_factory=list)
    quote: EGXStockQuote | None = None

    @field_validator("indices", mode="before")
    @classmethod
    def index_codes(
        cls,
        value: list[object],
    ) -> list[object]:
        return [getattr(index, "code", index) for index in value]

    @classmethod
    def from_market_watch_row(
        cls,
        row: EGXStockMarketWatchRow,
    ) -> "EGXStock":
        if row.isin is None:
            raise ValueError(
                "a market watch row without an isin is not a stock",
            )

        return cls(
            isin=row.isin,
            reuters=row.reuters,
            name=row.name,
            name_ar=row.name_ar,
            market_code=row.market_code,
            sector=(
                EGXStockSector(
                    egx_id=row.sec_id,
                    name=row.sector,
                    name_ar=row.sector_ar,
                )
                if row.sec_id is not None
                else None
            ),
            currency=(
                EGXStockCurrency(
                    code=row.currency_short,
                    code_ar=row.currency_short_ar,
                    name=row.currency,
                    name_ar=row.currency_ar,
                )
                if row.currency_short is not None
                else None
            ),
            funds_code=row.funds_code,
            is_intraday=row.intraday == "Y",
            has_history=row.with_history == "Y",
            indices=sorted(
                field.upper() for field in INDEX_FIELDS if getattr(row, field) == "Y"
            ),
            quote=(
                EGXStockQuote(
                    quoted_at=row.write_time,
                    trade_date=row.last_trade_date,
                    last_price=row.last_price,
                    open_price=row.open_price,
                    close_price=row.close_price,
                    prev_close=row.prev_close,
                    high=row.high,
                    low=row.low,
                    change_percent=row.change_percent,
                    value=row.value,
                    volume=row.volume,
                    trades=row.trades,
                    market_cap=row.market_cap,
                    net_profit=row.net_profit,
                )
                if row.write_time is not None
                else None
            ),
        )


def is_common_stock(
    row: EGXStockMarketWatchRow,
) -> bool:
    return row.symbol_type == EGXSymbolTypes.COMMON_STOCK and row.isin is not None


class EGXStockDailyClose(BaseModel):
    trade_date: date
    open_price: float | None = None
    high: float | None = None
    low: float | None = None
    close_price: float | None = None
    volume: int | None = None


class EGXStockPricePoint(BaseModel):
    timestamp: datetime
    price: float | None = None
    volume: int | None = None


class EGXStockDailyPoint(EGXStockPricePoint):
    # for a candle, a day backfilled from egx's history has none
    open: float | None = None
    high: float | None = None
    low: float | None = None


class EGXStockHistory(BaseModel):
    isin: str
    period: HistoryPeriods
    interval: PriceIntervals
    points: list[EGXStockDailyPoint | EGXStockPricePoint] = Field(default_factory=list)


class EGXStockPerformance(BaseModel):
    isin: str
    base_date: date
    base_close: float
    volume: int
    value: float
    latest_volume: int
    latest_value: float


class EGXStocksPerformance(BaseModel):
    period: PerformancePeriods
    since: date | None = None
    latest: date | None = None
    stocks: list[EGXStockPerformance] = Field(default_factory=list)
