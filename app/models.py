from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .utils import utcnow


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnonMessage(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(BigInteger)
    recipient_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(String(4096))
    # согласие отправителя на раскрытие при оплате получателем
    reveal_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    amount_kop: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="paid")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class AdminSession(Base):
    __tablename__ = "admin_sessions"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    since: Mapped[datetime] = mapped_column(DateTime, default=utcnow)