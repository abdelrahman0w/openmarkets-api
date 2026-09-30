from datetime import date
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


PRICE = Numeric(18, 4)
AMOUNT = Numeric(24, 4)
PERCENT = Numeric(10, 4)


class EGXStockQuote(Base):
    __tablename__ = "egx_stock_quotes"
    __table_args__ = (
        UniqueConstraint("stock_id", "quoted_at"),
        Index(None, "stock_id", "trade_date", "quoted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("egx_stocks.id", ondelete="CASCADE"),
    )
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trade_date: Mapped[date | None] = mapped_column(Date)
    last_price: Mapped[Decimal | None] = mapped_column(PRICE)
    open_price: Mapped[Decimal | None] = mapped_column(PRICE)
    close_price: Mapped[Decimal | None] = mapped_column(PRICE)
    prev_close: Mapped[Decimal | None] = mapped_column(PRICE)
    high: Mapped[Decimal | None] = mapped_column(PRICE)
    low: Mapped[Decimal | None] = mapped_column(PRICE)
    change_percent: Mapped[Decimal | None] = mapped_column(PERCENT)
    value: Mapped[Decimal | None] = mapped_column(AMOUNT)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    trades: Mapped[int | None] = mapped_column(Integer)
    market_cap: Mapped[Decimal | None] = mapped_column(AMOUNT)
    net_profit: Mapped[Decimal | None] = mapped_column(AMOUNT)


class EGXStockDailyPrice(Base):
    __tablename__ = "egx_stock_daily_prices"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("egx_stocks.id", ondelete="CASCADE"),
    )
    trade_date: Mapped[date] = mapped_column(Date)
    open_price: Mapped[Decimal | None] = mapped_column(PRICE)
    high: Mapped[Decimal | None] = mapped_column(PRICE)
    low: Mapped[Decimal | None] = mapped_column(PRICE)
    close_price: Mapped[Decimal | None] = mapped_column(PRICE)
    volume: Mapped[int | None] = mapped_column(BigInteger)
