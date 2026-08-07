import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web
from app.config import settings
from app.handlers import user, admin
from app.repo import init_db
from app.scheduler import start_scheduler
from aiohttp_socks import ProxyConnector
import aiohttp

logging.basicConfig(level=logging.INFO)

async def create_bot_session():
    """Создает сессию для бота с учетом настроек прокси"""
    if settings.proxy_url:
        try:
            # Формируем строку прокси для aiohttp_socks
            proxy_str = settings.proxy_url
            if settings.proxy_user and settings.proxy_password:
                # Вставляем логин/пароль в URL если они заданы отдельно
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(settings.proxy_url)
                netloc = f"{settings.proxy_user}:{settings.proxy_password}@{parsed.hostname}:{parsed.port}"
                proxy_str = urlunparse(parsed._replace(netloc=netloc))
            
            connector = ProxyConnector.from_url(proxy_str)
            aiohttp_session = aiohttp.ClientSession(connector=connector)
            
            logging.info(f"🌐 Telegram через прокси: {proxy_str.split('@')[1] if '@' in proxy_str else settings.proxy_url}")
            return AiohttpSession(session=aiohttp_session)
        except Exception as e:
            logging.warning(f"⚠️ Не удалось подключиться через прокси ({e}), переключаемся на прямое подключение...")
            if 'aiohttp_session' in locals():
                await aiohttp_session.close()

    logging.info("🌐 Прямое подключение к Telegram")
    return AiohttpSession()

async def on_startup(app):
    await init_db()
    start_scheduler(app['bot'])

async def main():
    # Создаем правильную сессию aiogram
    aiogram_session = await create_bot_session()
    
    bot = Bot(token=settings.bot_token, session=aiogram_session)
    dp = Dispatcher()
    
    dp.include_router(user.router)
    dp.include_router(admin.router)
    
    # Веб-сервер для хелсчеков или вебхуков (если понадобится)
    app = web.Application()
    app['bot'] = bot
    app.on_startup.append(on_startup)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', settings.webhook_port)
    await site.start()
    logging.info(f"✅ Веб-сервер запущен на порту {settings.webhook_port}")
    
    logging.info("✅ Бот запущен, поллинг…")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")