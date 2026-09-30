import calendar
from datetime import date
from datetime import timedelta
from enum import StrEnum


def _months_before(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1

    return day.replace(
        year=year,
        month=month,
        day=min(day.day, calendar.monthrange(year, month)[1]),
    )


class PerformancePeriods(StrEnum):
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    YEAR_TO_DATE = "ytd"
    ONE_YEAR = "1y"

    def since(self, latest: date) -> date:
        if self is PerformancePeriods.ONE_WEEK:
            return latest - timedelta(weeks=1)
        if self is PerformancePeriods.YEAR_TO_DATE:
            return date(latest.year - 1, 12, 31)

        months = {
            PerformancePeriods.ONE_MONTH: 1,
            PerformancePeriods.THREE_MONTHS: 3,
            PerformancePeriods.SIX_MONTHS: 6,
            PerformancePeriods.ONE_YEAR: 12,
        }

        return _months_before(latest, months[self])
