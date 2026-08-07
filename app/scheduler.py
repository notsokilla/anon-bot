from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.repo import get_auto_broadcast_templates, engine, User
from app.config import settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import asyncio

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
bot_instance = None

async def run_scheduled_broadcasts():
    if not bot_instance:
        logger.error("Бот не инициализирован для рассылки.")
        return

    templates = await get_auto_broadcast_templates()
    if not templates:
        return

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session_maker() as session:
        stmt = select(User.tg_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()
    
    for tmpl in templates:
        kb = None
        if tmpl.has_button and tmpl.button_url:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=tmpl.button_text, url=tmpl.button_url)
            ]])
        
        count = 0
        for uid in user_ids:
            try:
                if tmpl.image_id:
                    await bot_instance.send_photo(uid, photo=tmpl.image_id, caption=tmpl.text, reply_markup=kb)
                else:
                    await bot_instance.send_message(uid, tmpl.text, reply_markup=kb)
                count += 1
            except Exception:
                pass # Игнорируем ошибки отправки конкретному юзеру (блок, стоп)
            await asyncio.sleep(0.05)
        
        logger.info(f"Рассылка шаблона {tmpl.id}: отправлено {count}/{len(user_ids)}")

def start_scheduler(bot):
    global bot_instance
    bot_instance = bot
    
    if settings.scheduled_broadcast_cron:
        try:
            # Поддержка формата "мин час день мес день_нед" (стандарт cron)
            # Если в .env 5 значений, APScheduler поймет.
            trigger = CronTrigger.from_crontab(settings.scheduled_broadcast_cron)
            scheduler.add_job(run_scheduled_broadcasts, trigger=trigger, id="auto_broadcast")
            scheduler.start()
            logger.info(f"⏰ Авто-рассылка активирована: {settings.scheduled_broadcast_cron}")
        except Exception as e:
            logger.error(f"❌ Ошибка настройки крона: {e}")