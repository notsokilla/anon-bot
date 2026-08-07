import asyncio

from sqlalchemy import select

from ..db import Session
from ..models import AnonMessage, BroadcastTemplate, User
from aiogram.types import InlineKeyboardMarkup


async def send_broadcast(bot, text: str) -> int:
    """Ручная рассылка админа — без префикса."""
    async with Session() as s:
        ids = (await s.execute(select(User.id))).scalars().all()
    return await _fanout(bot, ids, text)


async def send_broadcast_with_kb(bot, text: str, kb: InlineKeyboardMarkup) -> int:
    """Рассылка с кнопкой (например, для премиум)."""
    async with Session() as s:
        ids = (await s.execute(select(User.id))).scalars().all()
    return await _fanout_with_kb(bot, ids, text, kb)


async def send_auto_broadcasts(bot) -> int:
    """Авто-рассылка по шаблонам с флагом use_in_auto=True"""
    from ..repo import get_auto_broadcast_templates
    templates = await get_auto_broadcast_templates()
    total_sent = 0

    for template in templates:
        async with Session() as s:
            ids = (await s.execute(select(User.id))).scalars().all()

        if template.has_button and template.button_url:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=template.button_text, url=template.button_url)],
            ])
            sent = await _fanout_with_photo_and_kb(bot, ids, template.text, template.image_id, kb)
        elif template.image_id:
            sent = await _fanout_with_photo(bot, ids, template.text, template.image_id)
        else:
            sent = await _fanout(bot, ids, template.text)

        total_sent += sent
        await asyncio.sleep(1)  # Пауза между шаблонами

    return total_sent


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


async def _fanout_with_kb(bot, ids, body: str, kb: InlineKeyboardMarkup) -> int:
    sent = 0
    for uid in ids:
        try:
            await bot.send_message(uid, body, reply_markup=kb)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    return sent


async def _fanout_with_photo(bot, ids, body: str, image_id: str | None) -> int:
    sent = 0
    for uid in ids:
        try:
            if image_id:
                await bot.send_photo(uid, photo=image_id, caption=body)
            else:
                await bot.send_message(uid, body)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    return sent


async def _fanout_with_photo_and_kb(bot, ids, body: str, image_id: str | None, kb: InlineKeyboardMarkup) -> int:
    sent = 0
    for uid in ids:
        try:
            if image_id:
                await bot.send_photo(uid, photo=image_id, caption=body, reply_markup=kb)
            else:
                await bot.send_message(uid, body, reply_markup=kb)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    return sent