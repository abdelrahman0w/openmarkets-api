from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


class EGXIndex(Base):
    __tablename__ = "egx_indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)


class EGXStockIndex(Base):
    __tablename__ = "egx_stock_indices"

    stock_id: Mapped[int] = mapped_column(
        ForeignKey("egx_stocks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    index_id: Mapped[int] = mapped_column(
        ForeignKey("egx_indices.id", ondelete="CASCADE"),
        primary_key=True,
    )
