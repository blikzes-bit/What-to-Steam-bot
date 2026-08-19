from functools import lru_cache

from pydantic import Field
from pydantic_settings import (  # pyright: ignore[reportMissingImports]
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(min_length=10)
    steam_api_key: str = Field(min_length=8)
    database_url: str = "postgresql+asyncpg://vochto:change_me@localhost:5432/vochto"
    price_country: str = "UA"
    price_language: str = "russian"
    deal_check_interval_minutes: int = Field(default=30, ge=5, le=1440)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
