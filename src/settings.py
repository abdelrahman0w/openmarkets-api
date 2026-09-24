from pydantic import Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy import URL


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        validate_default=True,
        extra="ignore",
    )


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


class Settings(BaseAppSettings):
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)


settings = Settings()
