import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    admin_password: str = ""
    proxy_url: str = ""
    proxy_user: str = ""
    proxy_password: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    landing_url: str = "https://example.com/reveal"
    token_secret: str = "change_me_long_random_string"
    webhook_port: int = 8080
    scheduled_broadcast_cron: str = ""  # Формат Cron: сек мин час день мес день_нед

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def admin_list(self):
        # Возвращаем пустой список, так как теперь используем пароль
        return []

    @property
    def proxy_dict(self) -> Optional[dict]:
        if not self.proxy_url:
            return None
        
        # Парсинг URL прокси для aiohttp_socks
        # Ожидаемый формат в .env: socks5://user:pass@host:port или socks5://host:port
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.proxy_url)
            
            username = self.proxy_user or parsed.username
            password = self.proxy_password or parsed.password
            hostname = parsed.hostname
            port = parsed.port or 1080
            
            if not hostname:
                return None

            proxy_str = f"{parsed.scheme}://"
            if username and password:
                proxy_str += f"{username}:{password}@"
            proxy_str += f"{hostname}:{port}"
            
            return {
                "proxy": proxy_str
            }
        except Exception:
            return None

settings = Settings()