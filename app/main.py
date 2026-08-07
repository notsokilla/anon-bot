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

async def create_session():
    if settings.proxy_dict:
        try:
            connector = ProxyConnector.from_url(settings.proxy_dict['proxy'])
            session = aiohttp.ClientSession(connector=connector)
            logging.info(f"🌐 Telegram через прокси: {settings.proxy_url.split('@')[1] if '@' in settings.proxy_url else settings.proxy_url}")
            return session
        except Exception as e:
            logging.warning(f"⚠️ Не удалось подключиться через прокси ({e}), переключаемся на прямое подключение...")
    
    logging.info("🌐 Прямое подключение к Telegram")
    return aiohttp.ClientSession()

async def on_startup(app):
    await init_db()
    start_scheduler(app['bot'])

async def main():
    session = await create_session()
    bot = Bot(token=settings.bot_token, session=AiohttpSession(session=session))
    dp = Dispatcher()
    
    dp.include_router(user.router)
    dp.include_router(admin.router)
    
    app = web.Application()
    app['bot'] = bot
    app.on_startup.append(on_startup)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', settings.webhook_port)
    await site.start()
    logging.info(f"✅ Вебхук для ленда поднят на порту {settings.webhook_port}")
    
    logging.info("✅ Бот запущен, поллинг…")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")