from datetime import datetime
from typing import Any

from sqlalchemy import DDL
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Computed
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.structs.tables.base import Base


SEARCH_TEXT = " || ' ' || ".join(
    f"coalesce({column}, '')"
    for column in (
        "heading",
        "heading_ar",
        "company_name",
        "company_name_ar",
        "content",
        "content_ar",
    )
)
HAS_PDF = (
    "coalesce(content, '') ilike '%.pdf%' or coalesce(content_ar, '') ilike '%.pdf%'"
)

event.listen(
    Base.metadata, "before_create", DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm")
)


class EGXNews(Base):
    __tablename__ = "egx_news"
    __table_args__ = (
        Index(None, "date_stamp", "code"),
        Index(None, "isin", "date_stamp"),
        Index(None, "sec_id", "date_stamp"),
        Index(None, "has_pdf", "date_stamp"),
        Index(
            None,
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[int] = mapped_column(BigInteger, unique=True)
    date_stamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heading: Mapped[str | None] = mapped_column(Text)
    heading_ar: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    content_ar: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(255))
    section_ar: Mapped[str | None] = mapped_column(String(255))
    sec_id: Mapped[int | None] = mapped_column(Integer)
    sector_id: Mapped[int | None] = mapped_column(Integer)
    material: Mapped[int | None] = mapped_column(Integer)
    egx: Mapped[int | None] = mapped_column(Integer)
    isin: Mapped[str | None] = mapped_column(String(16))
    company_name: Mapped[str | None] = mapped_column(Text)
    company_name_ar: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    search_text: Mapped[str | None] = mapped_column(Text, Computed(SEARCH_TEXT))
    has_pdf: Mapped[bool | None] = mapped_column(Boolean, Computed(HAS_PDF))


class EGXNewsSummary(Base):
    __tablename__ = "egx_news_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    news_code: Mapped[int] = mapped_column(
        ForeignKey("egx_news.code", ondelete="CASCADE"),
        unique=True,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    summary_ar: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    key_points_ar: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(String(64))
    read_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
