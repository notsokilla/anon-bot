import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .db import init_db
from .handlers import admin, user
from .services.broadcast import send_broadcast, send_unread_reminders
from .services.proxy import create_telegram_session
from .services.webhook import start_webhook

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def scheduled(bot: Bot):
    """Задача по крону: напоминание о непрочитанных + опциональное промо с подписью."""
    await send_unread_reminders(bot)
    if settings.scheduled_broadcast_text:
        await send_broadcast(bot, settings.scheduled_broadcast_text)


async def main():
    Path("data").mkdir(exist_ok=True)
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        session=create_telegram_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_routers(user.router, admin.router)

    await start_webhook()  # POST /api/paid — ленд отмечает оплаты
    logger.info("✅ Вебхук для ленда поднят на порту %s", settings.webhook_port)

    if settings.scheduled_broadcast_cron:
        # При необходимости поменяй UTC на Europe/Moscow
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            scheduled,
            CronTrigger.from_crontab(settings.scheduled_broadcast_cron),
            kwargs={"bot": bot},
        )
        scheduler.start()
        logger.info("⏰ Планировщик рассылки запущен: %s", settings.scheduled_broadcast_cron)

    logger.info("✅ Бот запущен, поллинг…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())