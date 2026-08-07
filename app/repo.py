from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import uuid
import os
from pathlib import Path
from .models import Base, User, AnonymousMessage, PendingMessage, AdminSession, BroadcastTemplate
from .config import settings

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Формируем правильный путь к базе данных
db_path = DATA_DIR / "bot.db"
database_url = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(database_url, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Создаем стандартный шаблон, если его нет
    async with async_session_maker() as session:
        result = await session.execute(select(BroadcastTemplate).where(BroadcastTemplate.text == "💌 Вам пришло новое анонимное сообщение!"))
        template = result.scalar_one_or_none()
        
        if not template:
            default_template = BroadcastTemplate(
                text="💌 Вам пришло новое анонимное сообщение!\n\nНажмите кнопку ниже, чтобы узнать, кто это мог быть 👇",
                image_id=None,
                use_in_auto=False, # По умолчанию выключено
                has_button=True,
                button_text="Узнать кто",
                button_url=settings.landing_url
            )
            session.add(default_template)
            await session.commit()

async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    """Получить пользователя по юзернейму (без @)"""
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_broadcast_template_by_id(session: AsyncSession, template_id: int) -> Optional[BroadcastTemplate]:
    """Получить шаблон рассылки по ID"""
    result = await session.execute(select(BroadcastTemplate).where(BroadcastTemplate.id == template_id))
    return result.scalar_one_or_none()

async def get_or_create_user(tg_id: int, username: str = None, first_name: str = None, last_name: str = None):
    async with async_session_maker() as session:
        user = await session.get(User, tg_id) # Используем tg_id как PK в модели, но в БД может быть id. Проверим модель.
        # В модели User id - PK, tg_id - unique. Исправим логику поиска.
        
        stmt = select(User).where(User.tg_id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Проверяем_pending сообщения для нового пользователя
            await deliver_pending_messages(session, tg_id)
            
        else:
            # Обновляем имя/юзернейм
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            if last_name and user.last_name != last_name:
                user.last_name = last_name
            await session.commit()
            
        return user

async def deliver_pending_messages(session, tg_id: int):
    """Доставляет отложенные сообщения пользователю при входе"""
    stmt = select(PendingMessage).where(PendingMessage.recipient_tg_id == tg_id)
    result = await session.execute(stmt)
    pending = result.scalars().all()
    
    if pending:
        # Возвращаем список сообщений, чтобы хендлер мог их отправить
        # Но в рамках этой функции мы просто помечаем их как доставленные или удаляем?
        # Лучше вернуть их списком, а удаление сделать после успешной отправки в хендлере.
        # Для упрощения: вернем объекты, а удалим их отдельно.
        pass
    
    return pending

async def add_pending_message(recipient_tg_id: int, sender_tg_id: int, text: str, file_id: str, content_type: str):
    async with async_session_maker() as session:
        msg = PendingMessage(
            recipient_tg_id=recipient_tg_id,
            sender_tg_id=sender_tg_id,
            content_text=text,
            content_file_id=file_id,
            content_type=content_type
        )
        session.add(msg)
        await session.commit()
        return msg

async def delete_pending_message(msg_id: int):
    async with async_session_maker() as session:
        await session.delete(await session.get(PendingMessage, msg_id))
        await session.commit()

async def save_message(sender_id: int, recipient_id: int, text: str, file_id: str, content_type: str):
    async with async_session_maker() as session:
        msg = AnonymousMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content_text=text,
            content_file_id=file_id,
            content_type=content_type
        )
        session.add(msg)
        await session.commit()
        return msg

async def get_unread_count(user_id: int):
    async with async_session_maker() as session:
        stmt = select(func.count()).select_from(AnonymousMessage).where(
            AnonymousMessage.recipient_id == user_id,
            AnonymousMessage.is_read == False
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

async def get_unread_messages(user_id: int):
    async with async_session_maker() as session:
        stmt = select(AnonymousMessage).where(
            AnonymousMessage.recipient_id == user_id,
            AnonymousMessage.is_read == False
        ).order_by(AnonymousMessage.created_at.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

async def mark_messages_read(messages_ids: list[int]):
    async with async_session_maker() as session:
        for msg_id in messages_ids:
            msg = await session.get(AnonymousMessage, msg_id)
            if msg:
                msg.is_read = True
        await session.commit()

async def stats():
    async with async_session_maker() as session:
        users_count = await session.execute(select(func.count(User.id)))
        msgs_count = await session.execute(select(func.count(AnonymousMessage.id)))
        unread_count = await session.execute(
            select(func.count(AnonymousMessage.id)).where(AnonymousMessage.is_read == False)
        )
        return {
            "users": users_count.scalar() or 0,
            "messages": msgs_count.scalar() or 0,
            "unread": unread_count.scalar() or 0
        }

# --- Admin Session ---
async def create_admin_session(user_id: int, ttl_minutes: int = 30):
    async with async_session_maker() as session:
        token = str(uuid.uuid4())
        now = datetime.utcnow()
        expires = now + timedelta(minutes=ttl_minutes)
        
        # Удаляем старые сессии
        await session.execute(delete(AdminSession).where(AdminSession.user_id == user_id))
        
        sess = AdminSession(user_id=user_id, token=token, created_at=now, expires_at=expires)
        session.add(sess)
        await session.commit()
        return token

async def is_admin_session(user_id: int):
    async with async_session_maker() as session:
        now = datetime.utcnow()
        stmt = select(AdminSession).where(
            AdminSession.user_id == user_id,
            AdminSession.expires_at > now
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

async def invalidate_admin_session(user_id: int):
    async with async_session_maker() as session:
        await session.execute(delete(AdminSession).where(AdminSession.user_id == user_id))
        await session.commit()

# --- Broadcast Templates ---
async def get_broadcast_templates():
    async with async_session_maker() as session:
        stmt = select(BroadcastTemplate).order_by(BroadcastTemplate.created_at.desc())
        result = await session.execute(stmt)
        return result.scalars().all()

async def get_auto_broadcast_templates():
    async with async_session_maker() as session:
        stmt = select(BroadcastTemplate).where(BroadcastTemplate.use_in_auto == True)
        result = await session.execute(stmt)
        return result.scalars().all()

async def create_broadcast_template(text: str, image_id: str = None, use_in_auto: bool = False, 
                                    has_button: bool = False, button_text: str = "Узнать", button_url: str = None):
    async with async_session_maker() as session:
        tmpl = BroadcastTemplate(
            text=text,
            image_id=image_id,
            use_in_auto=use_in_auto,
            has_button=has_button,
            button_text=button_text,
            button_url=button_url or settings.landing_url
        )
        session.add(tmpl)
        await session.commit()
        await session.refresh(tmpl)
        return tmpl

async def update_broadcast_template(tmpl_id: int, **kwargs):
    async with async_session_maker() as session:
        tmpl = await session.get(BroadcastTemplate, tmpl_id)
        if tmpl:
            for key, value in kwargs.items():
                if hasattr(tmpl, key):
                    setattr(tmpl, key, value)
            await session.commit()
            await session.refresh(tmpl)
        return tmpl

async def delete_broadcast_template(tmpl_id: int):
    async with async_session_maker() as session:
        tmpl = await session.get(BroadcastTemplate, tmpl_id)
        if tmpl:
            await session.delete(tmpl)
            await session.commit()
            return True
        return False
async def get_broadcast_template_by_id(tmpl_id: int):
    async with async_session_maker() as session:
        return await session.get(BroadcastTemplate, tmpl_id)
