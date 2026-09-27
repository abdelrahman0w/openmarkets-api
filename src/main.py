from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.exceptions import register_exception_handlers
from src.middlewares import LogsContextualizerMiddleware
from src.middlewares import RateLimitMiddleware
from src.providers import DatabaseConnection
from src.providers import DatabaseSessions
from src.providers import RedisConnection
from src.providers import enable_async_error_tracking
from src.providers import logger
from src.providers import setup_error_tracking
from src.providers import setup_logging
from src.routes import egx_router
from src.routes import health_router
from src.services import EGXConnection
from src.settings import settings
from src.utils import connect_singletons


setup_logging(
    level=settings.app.log_level,
    json_logs=settings.app.log_json,
)
setup_error_tracking(
    settings.error_tracking,
    settings.app,
)


SINGLETONS = (
    DatabaseConnection,
    DatabaseSessions,
    RedisConnection,
    EGXConnection,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    enable_async_error_tracking()

    async with connect_singletons(*SINGLETONS):
        logger.info(
            "[API Lifecycle] Started The API",
            environment=settings.app.environment,
            app_version=settings.app.version,
        )

        yield

    logger.info(
        "[API Lifecycle] Stopped The API",
        environment=settings.app.environment,
        app_version=settings.app.version,
    )


app = FastAPI(
    title="Open Markets API",
    description="Public market data from regional exchanges",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

register_exception_handlers(app)

app.add_middleware(
    RateLimitMiddleware,
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=1,
)
app.add_middleware(
    LogsContextualizerMiddleware,
)

app.include_router(health_router)
app.include_router(egx_router)
