from datetime import time
from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy import URL


VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def _built_version() -> str | None:
    if VERSION_FILE.is_file():
        return VERSION_FILE.read_text().strip() or None

    return None


class Environment(StrEnum):
    DEV = "DEV"
    PROD = "PROD"


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        validate_default=True,
        extra="ignore",
    )


class AppSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
    )

    environment: Environment = Environment.DEV
    version: str | None = Field(default_factory=_built_version)
    log_level: str = "INFO"
    log_json: bool = True


class DatabaseSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
    )

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    name: str

    @property
    def url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.name,
        )


class RedisSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
    )

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None
    cache_ttl_seconds: int = Field(default=300, ge=1)
    live_cache_seconds: int = Field(default=30, ge=1)


class ErrorTrackingSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="ERROR_TRACKING_",
    )

    dsn: SecretStr | None = None
    traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    logs_enabled: bool = True


class RateLimitSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="RATE_LIMIT_",
    )

    enabled: bool = True
    requests: int = Field(default=120, ge=1)
    window_seconds: int = Field(default=60, ge=1)
    timeout_seconds: float = Field(default=0.5, gt=0)
    client_ip_header: str = "CF-Connecting-IP"


class EGXMarketSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_prefix="EGX_MARKET_",
    )

    timezone: str = "Africa/Cairo"
    open_time: time = time(10, 0)
    close_time: time = time(14, 30)
    trading_days: frozenset[int] = frozenset({6, 0, 1, 2, 3})
    sync_grace_minutes: int = 30
    use_live_status: bool = True
    status_retry_minutes: int = Field(default=15, ge=0)
    status_retry_seconds: int = Field(default=60, ge=10)
    live_prices_cache_seconds: int = Field(default=10, ge=1)
    quote_retention_days: int = Field(default=30, ge=8)
    request_timeout_seconds: float = Field(default=10.0, gt=0)


class Settings(BaseAppSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    error_tracking: ErrorTrackingSettings = Field(
        default_factory=ErrorTrackingSettings,
    )
    egx_market: EGXMarketSettings = Field(default_factory=EGXMarketSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)


settings = Settings()
