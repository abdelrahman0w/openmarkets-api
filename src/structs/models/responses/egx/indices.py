from datetime import date
from datetime import datetime

from openmarkets.exchanges.egx.structs.models.responses.indices import EGXIndexDailyBar
from openmarkets.exchanges.egx.structs.models.responses.indices import EGXIndexData
from openmarkets.exchanges.egx.structs.models.responses.indices import (
    EGXIndexIntradayPoint,
)
from openmarkets.exchanges.egx.structs.models.responses.indices import EGXIndexSnapshot
from openmarkets.exchanges.egx.structs.models.responses.indices import EGXIndexSummary
from openmarkets.exchanges.egx.structs.models.responses.indices import EGXIndexWeight
from pydantic import BaseModel
from pydantic import Field

from src.structs.enums import EGXIndexName
from src.structs.enums import HistoryPeriods
from src.structs.enums import PerformancePeriods
from src.structs.enums import PriceIntervals


class EGXIndexValuePoint(BaseModel):
    timestamp: datetime
    value: float | None = None


class EGXIndexDailyPoint(EGXIndexValuePoint):
    open: float | None = None
    high: float | None = None
    low: float | None = None


class EGXIndexLevel(BaseModel):
    index: EGXIndexName
    title: str
    day: date | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    ytd_percent: float | None = None
    points: list[EGXIndexValuePoint] = Field(default_factory=list)


class EGXIndexHistory(BaseModel):
    index: EGXIndexName
    period: HistoryPeriods
    interval: PriceIntervals
    points: list[EGXIndexDailyPoint | EGXIndexValuePoint] = Field(default_factory=list)


__all__ = [
    "EGXIndexDailyBar",
    "EGXIndexDailyPoint",
    "EGXIndexData",
    "EGXIndexHistory",
    "EGXIndexIntradayPoint",
    "EGXIndexLevel",
    "EGXIndexSnapshot",
    "EGXIndexSummary",
    "EGXIndexValuePoint",
    "EGXIndexWeight",
]


class EGXIndexPerformance(BaseModel):
    index: EGXIndexName
    base_date: date
    base_close: float


class EGXIndicesPerformance(BaseModel):
    period: PerformancePeriods
    since: date | None = None
    indices: list[EGXIndexPerformance] = Field(default_factory=list)
