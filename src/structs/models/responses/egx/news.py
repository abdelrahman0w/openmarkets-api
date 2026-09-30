from datetime import datetime

from openmarkets.exchanges.egx.structs.models.responses.news import EGXNewsItem
from pydantic import BaseModel
from pydantic import Field


class EGXNewsSummary(BaseModel):
    summary: str
    summary_ar: str | None = None
    key_points: list[str] = Field(default_factory=list)
    key_points_ar: list[str] = Field(default_factory=list)
    model: str | None = None
    read_attachments: bool = False
    created_at: datetime | None = None


class EGXNewsItemDetail(EGXNewsItem):
    summary: EGXNewsSummary | None = None


__all__ = [
    "EGXNewsItem",
    "EGXNewsItemDetail",
    "EGXNewsSummary",
]
