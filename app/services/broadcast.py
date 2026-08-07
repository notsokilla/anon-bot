import asyncio

from sqlalchemy import select

from ..db import Session
from ..models import AnonMessage, User


async def send_broadcast(bot, text: str) -> int:
    """Ручная рассылка админа — всегда с подписью служебного уведомления."""
    body = "📣 <b>Служебное уведомление</b>\n\n" + text
    async with Session() as s:
        ids = (await s.execute(select(User.id))).scalars().all()
    return await _fanout(bot, ids, body)


async def send_unread_reminders(bot) -> int:
    """Авто-уведомление в стиле анонимного сообщения, но ONLY по факту:
    отправляется только тем, у кого действительно лежит непрочитанное сообщение."""
    async with Session() as s:
        ids = (await s.execute(
            select(AnonMessage.recipient_id).where(AnonMessage.is_read.is_(False))
        )).scalars().all()
    return await _fanout(bot, sorted(set(ids)),
                         "📨 <b>Тебя ждёт анонимное сообщение в боте</b> — зайди и открой его.")


async def _fanout(bot, ids, body: str) -> int:
    sent = 0
    for uid in ids:
        try:
            await bot.send_message(uid, body)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    return sent