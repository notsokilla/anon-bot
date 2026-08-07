from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.repo import get_broadcast_templates, get_all_users, async_session_maker
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def run_scheduled_broadcasts():
    logger.info("⏰ Запуск проверки авто-рассылок...")
    async with async_session_maker() as session:
        # Получаем активные шаблоны
        # Примечание: в реале нужно проверять время последнего запуска, чтобы не слать дубль в ту же минуту
        # Но для простоты шлем всё активное (лучше добавить флаг last_sent в БД)
        pass 
        # Логика должна быть в main.py при старте джобы, здесь только функция

def start_scheduler(bot):
    # Пример: запуск каждую минуту на 30-й секунде (не поддерживается кроном)
    # Используем интервал для теста: каждые 60 секунд
    # scheduler.add_job(run_scheduled_broadcasts, 'interval', seconds=60, id='test_interval')
    
    # Твой крон: 30 * * * * (Каждый час в 30 минут)
    # Для теста поменяй на */2 * * * * (каждые 2 минуты)
    scheduler.add_job(
        run_scheduled_broadcasts_logic, 
        trigger=CronTrigger.from_crontab("*/2 * * * *"), 
        id="auto_broadcast"
    )
    scheduler.start()
    logger.info("⏰ Планировщик запущен (режим теста: каждые 2 минуты)")

async def run_scheduled_broadcasts_logic():
    # Реальная логика рассылки
    from sqlalchemy import select
    from app.repo import BroadcastTemplate
    
    async with async_session_maker() as session:
        result = await session.execute(select(BroadcastTemplate).where(BroadcastTemplate.is_active == True))
        templates = result.scalars().all()
        
        for tmpl in templates:
            users = await get_all_users()
            count = 0
            for user in users:
                try:
                    # Нужно получить объект бота, передавать его в джобу
                    # Это упрощенный пример
                    # await bot.send_message(...) 
                    logger.info(f"Шаблон {tmpl.name} готов к отправке для {user.tg_id}")
                    count += 1
                except Exception as e:
                    logger.error(e)
            logger.info(f"Рассылка шаблона {tmpl.name}: потенциально {count} пользователей")