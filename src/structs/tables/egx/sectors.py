from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


class EGXSector(Base):
    __tablename__ = "egx_sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    egx_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
