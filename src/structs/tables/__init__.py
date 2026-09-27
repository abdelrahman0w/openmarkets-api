import importlib
import pkgutil

from .base import Base


for module in pkgutil.walk_packages(__path__, prefix=f"{__name__}."):
    importlib.import_module(module.name)

from .egx import EGXCurrency  # noqa: E402
from .egx import EGXIndex  # noqa: E402
from .egx import EGXSector  # noqa: E402
from .egx import EGXStock  # noqa: E402
from .egx import EGXStockDailyPrice  # noqa: E402
from .egx import EGXStockIndex  # noqa: E402
from .egx import EGXStockQuote  # noqa: E402


__all__ = [
    "Base",
    "EGXCurrency",
    "EGXIndex",
    "EGXSector",
    "EGXStock",
    "EGXStockDailyPrice",
    "EGXStockIndex",
    "EGXStockQuote",
]
