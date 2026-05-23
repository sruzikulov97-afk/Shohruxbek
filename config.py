from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    bot_token:       str
    bot_username:    str   = "@Shohrux_test_bot"
    admin_ids:       str   = "8302385031"
    webapp_url:      str   = "https://shohrux-production.up.railway.app/webapp"
    admin_password:  str   = "admin123"
    database_url:    str   = "sqlite+aiosqlite:///./data/bot.db"
    channel_id:      int   = 0
    channel_username:str   = ""
    log_level:       str   = "INFO"

    @property
    def admin_list(self) -> List[int]:
        return [int(i.strip()) for i in self.admin_ids.split(",") if i.strip().isdigit()]

    from pydantic import model_validator

    @model_validator(mode='after')
    def clean_webapp_url(self) -> 'Settings':
        url = self.webapp_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if not url.endswith("/webapp") and not url.endswith("/webapp/"):
            url = url.rstrip("/") + "/webapp"
        self.webapp_url = url
        return self

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
