from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    bot_token:       str
    bot_username:    str   = "@Shohrux_test_bot"
    admin_ids:       str   = "8302385031"
    sklad_ids:       str   = ""
    webapp_url:      str   = "https://shohrux-production.up.railway.app/webapp"
    admin_password:  str   = "admin123"
    database_url:    str   = "sqlite+aiosqlite:///./data/bot.db"
    channel_id:      int   = 0
    channel_username:str   = ""
    log_level:       str   = "INFO"
    google_service_account_json: str = ""
    google_service_account_file: str = ""
    google_sheet_id: str = ""

    @property
    def admin_list(self) -> List[int]:
        return [int(i.strip()) for i in self.admin_ids.split(",") if i.strip().isdigit()]

    @property
    def sklad_list(self) -> List[int]:
        return [int(i.strip()) for i in self.sklad_ids.split(",") if i.strip().isdigit()]

    from pydantic import model_validator

    @model_validator(mode='after')
    def clean_settings(self) -> 'Settings':
        # Clean webapp_url
        url = self.webapp_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if not url.endswith("/webapp") and not url.endswith("/webapp/"):
            url = url.rstrip("/") + "/webapp"
        self.webapp_url = url

        # Clean database_url for SQLAlchemy Async engine
        db_url = self.database_url.strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("sqlite://") and not db_url.startswith("sqlite+aiosqlite://"):
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        self.database_url = db_url

        return self

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
