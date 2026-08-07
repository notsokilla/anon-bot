"""Подключение бота к Telegram API через прокси.

Адаптировано из присланного bot.py:
- PROXY_URL — адрес прокси вида scheme://host:port;
- PROXY_USER / PROXY_PASSWORD — креды, если они не зашиты в сам URL;
- если в PROXY_URL уже есть "@" (креды внутри), креды из env не подмешиваются.

HTTP(S) работает из коробки; для SOCKS5 нужен aiohttp-socks (уже в requirements).
Если прокси недоступен — бот автоматически переключится на прямое подключение.
"""
import logging
import re

from aiogram.client.session.aiohttp import AiohttpSession

from ..config import settings

logger = logging.getLogger(__name__)


def _mask(url: str) -> str:
    """Скрывает пароль прокси в логах: scheme://user:***@host:port"""
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:***@", url)


def create_telegram_session() -> AiohttpSession:
    if not settings.proxy_url:
        logger.info("🌐 Telegram без прокси")
        return AiohttpSession()

    proxy_url = settings.proxy_url
    if settings.proxy_user and settings.proxy_password and "@" not in settings.proxy_url:
        scheme, rest = settings.proxy_url.split("://", 1)
        proxy_url = f"{scheme}://{settings.proxy_user}:{settings.proxy_password}@{rest}"

    logger.info("🌐 Telegram через прокси: %s", _mask(proxy_url))
    
    try:
        return AiohttpSession(proxy=proxy_url)
    except Exception as e:
        logger.warning("⚠️ Не удалось подключиться через прокси (%s), пробуем без прокси...", e)
        return AiohttpSession()