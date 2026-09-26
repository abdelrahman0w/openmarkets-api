from functools import partial
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.asyncio import enable_asyncio_integration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.providers.logger import logger
from src.settings import AppSettings
from src.settings import ErrorTrackingSettings


UNTRACED_PREFIXES = ("/health",)


def traces_sampler(context: dict[str, Any], *, rate: float) -> float:
    path = (context.get("asgi_scope") or {}).get("path", "")

    return 0.0 if path.startswith(UNTRACED_PREFIXES) else rate


def setup_error_tracking(
    error_tracking: ErrorTrackingSettings,
    app: AppSettings,
) -> None:
    if error_tracking.dsn is None:
        logger.info(
            "[Error Tracking] Disabled - DSN Is Not Set",
        )

        return

    sentry_sdk.init(
        dsn=error_tracking.dsn.get_secret_value(),
        environment=app.environment,
        release=app.version,
        traces_sampler=partial(
            traces_sampler,
            rate=error_tracking.traces_sample_rate,
        ),
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
            RedisIntegration(),
            HttpxIntegration(),
            LoguruIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
    )

    logger.info(
        "[Error Tracking] Enabled",
        environment=app.environment,
    )


def enable_async_error_tracking() -> None:
    if sentry_sdk.get_client().is_active():
        enable_asyncio_integration()
