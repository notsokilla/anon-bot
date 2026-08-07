from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str = ""
    admin_password: str = ""
    proxy_url: str = ""
    proxy_user: str = ""
    proxy_password: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    landing_url: str = "https://example.com/reveal"
    token_secret: str = "change_me"
    webhook_port: int = 8080
    scheduled_broadcast_cron: str = ""  # теперь не используется, только для обратной совместимости
    scheduled_broadcast_text: str = ""  # теперь не используется

    @property
    def admin_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.replace(",", " ").split()]


settings = Settings()