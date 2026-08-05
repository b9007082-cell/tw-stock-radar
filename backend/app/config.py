from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "台股起漲雷達"
    database_url: str = "sqlite:///./data/stock_scanner.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    strategy_version: str = "2026.08.v18"
    strategy_approved: bool = False
    intraday_scan_limit: int = 300
    timezone: str = "Asia/Taipei"
    twse_url: str = (
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    )
    tpex_url: str = (
        "https://www.tpex.org.tw/openapi/v1/"
        "tpex_mainboard_daily_close_quotes"
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
