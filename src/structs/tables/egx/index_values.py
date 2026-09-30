from datetime import date
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


LEVEL = Numeric(18, 4)
PERCENT = Numeric(10, 4)


class EGXIndexDailyBar(Base):
    __tablename__ = "egx_index_daily_bars"
    __table_args__ = (UniqueConstraint("index", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    index: Mapped[str] = mapped_column(String(32))
    day: Mapped[date] = mapped_column(Date)
    open: Mapped[Decimal | None] = mapped_column(LEVEL)
    high: Mapped[Decimal | None] = mapped_column(LEVEL)
    low: Mapped[Decimal | None] = mapped_column(LEVEL)
    close: Mapped[Decimal | None] = mapped_column(LEVEL)
    change: Mapped[Decimal | None] = mapped_column(LEVEL)
    change_percent: Mapped[Decimal | None] = mapped_column(PERCENT)
    ytd_percent: Mapped[Decimal | None] = mapped_column(PERCENT)


class EGXIndexPoint(Base):
    __tablename__ = "egx_index_points"
    __table_args__ = (UniqueConstraint("index", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    index: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[Decimal] = mapped_column(LEVEL)
