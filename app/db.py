from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import settings
from .models import Base, BroadcastTemplate

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Создаём стандартный шаблон авто-рассылки если его нет
    async with Session() as session:
        from sqlalchemy import select
        result = await session.execute(select(BroadcastTemplate))
        if not result.scalars().first():
            # Импортируем здесь чтобы избежать циклического импорта
            from .repo import create_broadcast_template
            # Стандартный шаблон "Вам пришло анонимное письмо"
            await create_broadcast_template(
                text="💌 Вам пришло новое анонимное сообщение!\n\nНажмите кнопку ниже, чтобы узнать, кто это мог быть 👇",
                has_button=True,
                button_text="Узнать кто",
                button_url=settings.landing_url,
                use_in_auto=False  # По умолчанию отключено, админ может включить вручную
            )