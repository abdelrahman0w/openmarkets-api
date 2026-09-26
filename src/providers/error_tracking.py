from contextlib import AbstractContextManager

import sentry_sdk
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration

from src.providers.logger import logger
from src.settings import AppSettings
from src.settings import ErrorTrackingSettings


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
        traces_sample_rate=error_tracking.traces_sample_rate,
        send_default_pii=False,
        integrations=[
            HttpxIntegration(),
            LoguruIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
    )

    logger.info(
        "[Error Tracking] Enabled",
        environment=app.environment,
    )
