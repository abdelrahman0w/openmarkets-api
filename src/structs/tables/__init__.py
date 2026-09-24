import importlib
import pkgutil

from src.structs.tables.base import Base


# import every table module, so all tables are registered on `Base.metadata`
for module in pkgutil.walk_packages(__path__, prefix=f"{__name__}."):
    importlib.import_module(module.name)

__all__ = [
    "Base",
]
