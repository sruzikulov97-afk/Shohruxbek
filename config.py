from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    bot_token:       str
    bot_username:    str   = "@ShohruxbeK_uchun_bot"
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

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
