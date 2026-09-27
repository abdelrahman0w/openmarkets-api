from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


class EGXCurrency(Base):
    __tablename__ = "egx_currencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    code_ar: Mapped[str | None] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(64))
    name_ar: Mapped[str | None] = mapped_column(String(64))
