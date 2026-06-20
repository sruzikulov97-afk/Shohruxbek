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
    report_group_id: str = ""

    @property
    def admin_list(self) -> List[int]:
        return [int(i.strip()) for i in self.admin_ids.split(",") if i.strip().isdigit()]

    @property
    def sklad_list(self) -> List[int]:
        return [int(i.strip()) for i in self.sklad_ids.split(",") if i.strip().isdigit()]

    from pydantic import model_validator

    @model_validator(mode='after')
    def clean_settings(self) -> 'Settings':
        # Strip literal quotes from string settings
        self.bot_token = self.bot_token.strip().strip("'").strip('"')
        self.bot_username = self.bot_username.strip().strip("'").strip('"')
        self.admin_ids = self.admin_ids.strip().strip("'").strip('"')
        self.sklad_ids = self.sklad_ids.strip().strip("'").strip('"')
        self.webapp_url = self.webapp_url.strip().strip("'").strip('"')
        self.admin_password = self.admin_password.strip().strip("'").strip('"')
        self.database_url = self.database_url.strip().strip("'").strip('"')
        self.google_service_account_json = self.google_service_account_json.strip().strip("'").strip('"')
        self.google_service_account_file = self.google_service_account_file.strip().strip("'").strip('"')
        self.google_sheet_id = self.google_sheet_id.strip().strip("'").strip('"')
        self.report_group_id = self.report_group_id.strip().strip("'").strip('"')

        # Clean webapp_url
        url = self.webapp_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if not url.endswith("/webapp") and not url.endswith("/webapp/"):
            url = url.rstrip("/") + "/webapp"
        self.webapp_url = url

        # Clean database_url for SQLAlchemy Async engine
        db_url = self.database_url.strip()
        if not db_url:
            db_url = "sqlite+aiosqlite:///./data/bot.db"
        
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
