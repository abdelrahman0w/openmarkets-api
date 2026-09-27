from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.structs.tables.base import Base
from src.structs.tables.egx.currencies import EGXCurrency
from src.structs.tables.egx.indices import EGXIndex
from src.structs.tables.egx.sectors import EGXSector


class EGXStock(Base):
    __tablename__ = "egx_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True)
    reuters: Mapped[str | None] = mapped_column(String(32), unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    market_code: Mapped[str | None] = mapped_column(String(16))
    sector_id: Mapped[int | None] = mapped_column(
        ForeignKey("egx_sectors.id", ondelete="SET NULL"),
        index=True,
    )
    currency_id: Mapped[int | None] = mapped_column(
        ForeignKey("egx_currencies.id", ondelete="SET NULL"),
        index=True,
    )
    funds_code: Mapped[int | None] = mapped_column(Integer)
    is_intraday: Mapped[bool] = mapped_column(Boolean, default=False)
    has_history: Mapped[bool] = mapped_column(Boolean, default=False)
    sector: Mapped[EGXSector | None] = relationship(lazy="raise")
    currency: Mapped[EGXCurrency | None] = relationship(lazy="raise")
    indices: Mapped[list[EGXIndex]] = relationship(
        secondary="egx_stock_indices",
        order_by=EGXIndex.code,
        lazy="raise",
    )
