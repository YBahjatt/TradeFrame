from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TradeFrame"
    database_url: str = f"sqlite:///{(Path(__file__).resolve().parents[2] / 'data' / 'tradeframe.sqlite3').as_posix()}"
    aleca_data_dir: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_prefix="TRADEFRAME_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
