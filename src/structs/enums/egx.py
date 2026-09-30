from enum import StrEnum

from openmarkets.exchanges.egx.structs.enums import EGXIndexInterval
from openmarkets.exchanges.egx.structs.enums import EGXIndexName
from openmarkets.exchanges.egx.structs.enums import EGXMarketStatusValue


class EGXSymbolTypes(StrEnum):
    COMMON_STOCK = "C"
    BOND = "B"


EGX_INDEX_TITLES: dict[EGXIndexName, str] = {
    EGXIndexName.EGX30: "EGX30",
    EGXIndexName.EGX30_USD: "EGX30 USD",
    EGXIndexName.EGX30_CAPPED: "EGX30 Capped",
    EGXIndexName.EGX30_TOTAL_RETURN: "EGX30 Total Return",
    EGXIndexName.EGX70_EWI: "EGX70 EWI",
    EGXIndexName.EGX100_EWI: "EGX100 EWI",
    EGXIndexName.EGX_SHARIAH: "EGX33 Shariah",
    EGXIndexName.EGX35_LOW_VOLATILITY: "EGX35 Low Volatility",
    EGXIndexName.TAMAYUZ: "Tamayuz",
}


__all__ = [
    "EGX_INDEX_TITLES",
    "EGXIndexInterval",
    "EGXIndexName",
    "EGXMarketStatusValue",
    "EGXSymbolTypes",
]
