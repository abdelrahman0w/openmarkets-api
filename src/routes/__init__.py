from .auth import router as auth_router
from .egx import router as egx_router
from .health import router as health_router


__all__ = [
    "auth_router",
    "egx_router",
    "health_router",
]
