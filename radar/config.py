from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RADAR_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_path: Path = Path("data/keys_radar.sqlite3")
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
