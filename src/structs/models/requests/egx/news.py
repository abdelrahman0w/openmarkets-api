from openmarkets import EGXFinancialStatementsRequest
from openmarkets import EGXNewsDetailRequest
from openmarkets import EGXNewsSearchRequest
from pydantic import BaseModel
from pydantic import Field


class EGXStoredNewsSearchRequest(EGXNewsSearchRequest):
    isin: str | None = Field(
        default=None,
        min_length=12,
        max_length=12,
    )
    has_attachments: bool = False

    @property
    def stored_only(self) -> bool:
        return self.isin is not None or self.has_attachments

    def for_egx(self) -> EGXNewsSearchRequest:
        return EGXNewsSearchRequest(
            **self.model_dump(exclude={"isin", "has_attachments"}),
        )


class EGXStockNewsRequest(BaseModel):
    isin: str
    page_number: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=250)


__all__ = [
    "EGXFinancialStatementsRequest",
    "EGXNewsDetailRequest",
    "EGXNewsSearchRequest",
    "EGXStockNewsRequest",
    "EGXStoredNewsSearchRequest",
]
