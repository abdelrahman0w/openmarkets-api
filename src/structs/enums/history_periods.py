from enum import StrEnum


class PriceIntervals(StrEnum):
    ONE_MINUTE = "1m"
    ONE_DAY = "1d"


class HistoryPeriods(StrEnum):
    ONE_DAY = "1d"
    THREE_DAYS = "3d"
    FIVE_DAYS = "5d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"
    TWO_MONTHS = "2m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"
    TWO_YEARS = "2y"
    THREE_YEARS = "3y"
    FIVE_YEARS = "5y"

    @property
    def interval(self) -> PriceIntervals:
        """Up to a week comes from the minute quotes, the rest from daily closes."""
        if self in _INTRADAY:
            return PriceIntervals.ONE_MINUTE

        return PriceIntervals.ONE_DAY

    @property
    def sessions(self) -> int | None:
        """How many trading sessions back a day based period reaches."""
        return _SESSIONS.get(self)

    @property
    def lookback(self) -> dict[str, int]:
        """The calendar offset back from the latest point, for the other periods."""
        return _LOOKBACKS.get(self, {})


_INTRADAY = {
    HistoryPeriods.ONE_DAY,
    HistoryPeriods.THREE_DAYS,
    HistoryPeriods.FIVE_DAYS,
    HistoryPeriods.ONE_WEEK,
}

# days are counted in trading sessions, since the market is closed on weekends
_SESSIONS = {
    HistoryPeriods.ONE_DAY: 1,
    HistoryPeriods.THREE_DAYS: 3,
    HistoryPeriods.FIVE_DAYS: 5,
}

_LOOKBACKS = {
    HistoryPeriods.ONE_WEEK: {"weeks": 1},
    HistoryPeriods.ONE_MONTH: {"months": 1},
    HistoryPeriods.TWO_MONTHS: {"months": 2},
    HistoryPeriods.THREE_MONTHS: {"months": 3},
    HistoryPeriods.SIX_MONTHS: {"months": 6},
    HistoryPeriods.ONE_YEAR: {"months": 12},
    HistoryPeriods.TWO_YEARS: {"months": 24},
    HistoryPeriods.THREE_YEARS: {"months": 36},
    HistoryPeriods.FIVE_YEARS: {"months": 60},
}
