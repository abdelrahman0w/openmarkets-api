from enum import StrEnum

from openmarkets.exchanges.egx.structs.enums import EGXMarketStatusValue


class EGXSymbolTypes(StrEnum):
    COMMON_STOCK = "C"
    BOND = "B"


__all__ = [
    "EGXMarketStatusValue",
    "EGXSymbolTypes",
]
