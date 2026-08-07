import os
from pathlib import Path
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_session_maker
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Integer, String, Boolean, DateTime, Text
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Создаем папку data если нет
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "bot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PendingMessage(Base):
    __tablename__ = "pending_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_tg_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True) # ID получателя
    recipient_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # Сохраняем юзернейм на всякий
    sender_tg_id: Mapped[int] = mapped_column(Integer, nullable=True) # Кто отправил (может быть None если системное)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class BroadcastTemplate(Base):
    __tablename__ = "broadcast_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Например "30 * * * *"

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Проверка и создание дефолтного шаблона ТОЛЬКО если их нет вообще
    async with async_session_maker() as session:
        result = await session.execute(select(BroadcastTemplate))
        templates = result.scalars().all()
        
        if not templates:
            default_tmpl = BroadcastTemplate(
                name="Ежедневная рассылка",
                text="💌 Вам пришло новое анонимное сообщение!",
                is_active=False,
                cron_schedule="30 * * * *"
            )
            session.add(default_tmpl)
            await session.commit()
            logger.info("✅ Создан шаблон рассылки по умолчанию")

async def get_or_create_user(tg_id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None, is_premium: bool = False) -> User:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_premium=is_premium
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"➕ Новый пользователь: {tg_id} (@{username})")
        else:
            # Обновляем данные если изменились
            if user.username != username or user.first_name != first_name:
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.is_premium = is_premium
                await session.commit()
        
        return user

async def get_user_by_tg_id(tg_id: int) -> Optional[User]:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        return result.scalar_one_or_none()

async def get_user_by_username(username: str) -> Optional[User]:
    """Ищет пользователя по юзернейму (без @)"""
    clean_username = username.lstrip('@')
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == clean_username))
        return result.scalar_one_or_none()

async def save_pending_message(recipient_tg_id: int, recipient_username: Optional[str], text: str, sender_tg_id: Optional[int] = None):
    async with async_session_maker() as session:
        msg = PendingMessage(
            recipient_tg_id=recipient_tg_id,
            recipient_username=recipient_username,
            text=text,
            sender_tg_id=sender_tg_id
        )
        session.add(msg)
        await session.commit()
        logger.info(f"💾 Сообщение сохранено для пользователя {recipient_tg_id} (@{recipient_username})")

async def get_pending_messages_for_user(tg_id: int, username: Optional[str] = None) -> List[PendingMessage]:
    async with async_session_maker() as session:
        # Ищем сообщения где:
        # 1. recipient_tg_id == tg_id (обычная доставка)
        # 2. ИЛИ recipient_tg_id == 0 И recipient_username == текущий username (доставка по юзернейму)
        
        conditions = [PendingMessage.recipient_tg_id == tg_id]
        if username:
            conditions.append(
                (PendingMessage.recipient_tg_id == 0) & (PendingMessage.recipient_username == username)
            )
        
        query = select(PendingMessage).where(conditions[0] if len(conditions) == 1 else (conditions[0] | conditions[1]))
        
        result = await session.execute(query)
        messages = result.scalars().all()
        
        if messages:
            for msg in messages:
                await session.delete(msg)
            await session.commit()
            logger.info(f"📬 Доставлено {len(messages)} отложенных сообщений для {tg_id}")
            
        return messages

async def get_all_users() -> List[User]:
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        return list(result.scalars().all())

# --- Шаблоны ---

async def get_broadcast_templates() -> List[BroadcastTemplate]:
    async with async_session_maker() as session:
        result = await session.execute(select(BroadcastTemplate).order_by(BroadcastTemplate.id))
        return list(result.scalars().all())

async def get_broadcast_template_by_id(tmpl_id: int) -> Optional[BroadcastTemplate]:
    async with async_session_maker() as session:
        result = await session.execute(select(BroadcastTemplate).where(BroadcastTemplate.id == tmpl_id))
        return result.scalar_one_or_none()

async def update_broadcast_template(tmpl_id: int, name: Optional[str] = None, text: Optional[str] = None, is_active: Optional[bool] = None, cron_schedule: Optional[str] = None):
    async with async_session_maker() as session:
        tmpl = await get_broadcast_template_by_id(tmpl_id)
        if tmpl:
            if name is not None: tmpl.name = name
            if text is not None: tmpl.text = text
            if is_active is not None: tmpl.is_active = is_active
            if cron_schedule is not None: tmpl.cron_schedule = cron_schedule
            await session.commit()
            await session.refresh(tmpl)
        return tmpl

async def add_broadcast_template(name: str, text: str, is_active: bool = False, cron_schedule: Optional[str] = None) -> BroadcastTemplate:
    async with async_session_maker() as session:
        tmpl = BroadcastTemplate(name=name, text=text, is_active=is_active, cron_schedule=cron_schedule)
        session.add(tmpl)
        await session.commit()
        await session.refresh(tmpl)
        return tmpl