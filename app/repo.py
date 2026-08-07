from sqlalchemy import func, select

from .db import Session
from .models import AdminSession, AnonMessage, Payment, User
from .utils import utcnow


async def upsert_user(tg) -> None:
    async with Session() as s:
        u = await s.get(User, tg.id)
        if u is None:
            s.add(User(id=tg.id, username=tg.username, first_name=tg.first_name))
        else:
            u.username = tg.username
            u.first_name = tg.first_name
            u.last_seen = utcnow()
        await s.commit()


async def find_user(raw: str):
    async with Session() as s:
        if raw.isdigit():
            return await s.get(User, int(raw))
        uname = raw.lstrip("@").lower()
        return (await s.execute(
            select(User).where(func.lower(func.coalesce(User.username, "")) == uname)
        )).scalar_one_or_none()


async def create_message(sender_id: int, recipient_id: int, text: str) -> AnonMessage:
    async with Session() as s:
        m = AnonMessage(sender_id=sender_id, recipient_id=recipient_id, text=text)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def get_message(mid: int):
    async with Session() as s:
        return await s.get(AnonMessage, mid)


async def set_message_reveal(mid: int, status: str):
    async with Session() as s:
        m = await s.get(AnonMessage, mid)
        if m:
            m.reveal_status = status
        await s.commit()


async def add_payment(user_id: int, message_id: int, amount_kop: int):
    async with Session() as s:
        s.add(Payment(user_id=user_id, message_id=message_id, amount_kop=amount_kop))
        await s.commit()


async def set_payment_consent(message_id: int, consent: str):
    async with Session() as s:
        p = (await s.execute(
            select(Payment).where(Payment.message_id == message_id).order_by(Payment.id.desc())
        )).scalars().first()
        if p:
            p.sender_consent = consent
        await s.commit()


async def payments_list(limit: int = 15):
    async with Session() as s:
        return (await s.execute(
            select(Payment).order_by(Payment.id.desc()).limit(limit)
        )).scalars().all()


async def stats() -> dict:
    async with Session() as s:
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "users_total": await s.scalar(select(func.count(User.id))),
            "users_today": await s.scalar(select(func.count(User.id)).where(User.started_at >= today)),
            "messages": await s.scalar(select(func.count(AnonMessage.id))),
            "payments_count": await s.scalar(select(func.count(Payment.id)).where(Payment.status == "paid")),
            "payments_sum": await s.scalar(
                select(func.coalesce(func.sum(Payment.amount_kop), 0)).where(Payment.status == "paid")),
            "reveal_yes": await s.scalar(select(func.count(AnonMessage.id)).where(AnonMessage.reveal_status == "yes")),
            "reveal_no": await s.scalar(select(func.count(AnonMessage.id)).where(AnonMessage.reveal_status == "no")),
            "reveal_pending": await s.scalar(select(func.count(AnonMessage.id)).where(AnonMessage.reveal_status == "pending")),
        }
    
async def create_message(sender_id: int, recipient_id: int, text: str, reveal_consent: bool) -> AnonMessage:
    async with Session() as s:
        m = AnonMessage(sender_id=sender_id, recipient_id=recipient_id,
                        text=text, reveal_consent=reveal_consent)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def mark_read(mid: int):
    async with Session() as s:
        m = await s.get(AnonMessage, mid)
        if m:
            m.is_read = True
        await s.commit()

async def is_admin_session(uid: int) -> bool:
    async with Session() as s:
        return (await s.get(AdminSession, uid)) is not None


async def add_admin_session(uid: int):
    async with Session() as s:
        if await s.get(AdminSession, uid) is None:
            s.add(AdminSession(user_id=uid))
        await s.commit()


async def remove_admin_session(uid: int):
    async with Session() as s:
        obj = await s.get(AdminSession, uid)
        if obj:
            await s.delete(obj)
        await s.commit()