import hmac
import time

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..repo import (add_admin_session, is_admin_session, payments_list,
                    remove_admin_session, stats)
from ..services.broadcast import send_broadcast

router = Router()

# Защита от перебора: {user_id: (число неудач, заблокировано до)}
_failures: dict[int, tuple[int, float]] = {}
MAX_FAILS, COOLDOWN = 5, 300


async def is_authorized(uid: int) -> bool:
    return uid in settings.admin_list or await is_admin_session(uid)


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        return event.from_user is not None and await is_authorized(event.from_user.id)


class AdminStates(StatesGroup):
    password = State()
    broadcast_text = State()


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
         InlineKeyboardButton(text="💳 Платежи", callback_data="adm:pays")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="adm:bc"),
         InlineKeyboardButton(text="🚪 Выход", callback_data="adm:logout")],
    ])


@router.message(Command("admin"))
async def admin(m: Message, state: FSMContext):
    if await is_authorized(m.from_user.id):
        return await m.answer("Админка.", reply_markup=admin_kb())
    if not settings.admin_password:
        return await m.answer("Доступ не настроен: ADMIN_PASSWORD пуст, ADMIN_IDS пуст.")
    await state.set_state(AdminStates.password)
    await m.answer("🔒 Введи пароль доступа.")


@router.message(Command("cancel"), AdminStates.password)
async def admin_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Отменено.")


@router.message(AdminStates.password)
async def admin_password(m: Message, state: FSMContext):
    uid = m.from_user.id
    count, until = _failures.get(uid, (0, 0.0))
    if time.time() < until:
        return await m.answer(f"Слишком много попыток. Подожди {int(until - time.time())} с.")

    got = (m.text or "").strip()
    if not hmac.compare_digest(got.encode(), settings.admin_password.encode()):
        count += 1
        if count >= MAX_FAILS:
            _failures[uid] = (0, time.time() + COOLDOWN)
            return await m.answer("Слишком много неудачных попыток — пауза 5 минут.")
        _failures[uid] = (count, 0.0)
        return await m.answer("Неверный пароль.")

    _failures.pop(uid, None)
    await state.clear()
    await add_admin_session(uid)
    try:
        await m.delete()  # не оставляем пароль в истории чата
    except Exception:
        pass
    await m.answer("✅ Доступ выдан.", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:logout")
async def logout(cq: CallbackQuery, state: FSMContext):
    await remove_admin_session(cq.from_user.id)
    await state.clear()
    await cq.answer("Вы вышли из админки.")


@router.callback_query(F.data == "adm:stats", IsAdmin())
async def stats_h(cq: CallbackQuery):
    s = await stats()
    text = (
        "📊 <b>Статистика</b>\n"
        f"Всего пользователей: {s['users_total']}\n"
        f"Новых сегодня: {s['users_today']}\n"
        f"Анонимных сообщений: {s['messages']} (непрочитанных: {s['unread']})\n"
        f"Платежей: {s['payments_count']} на {s['payments_sum'] / 100:.2f} ₽"
    )
    await cq.answer()
    await cq.message.answer(text)


@router.callback_query(F.data == "adm:pays", IsAdmin())
async def pays_h(cq: CallbackQuery):
    rows = await payments_list(15)
    if not rows:
        return await cq.answer("Платежей пока нет", show_alert=True)
    lines = [f"• {p.user_id} — {p.amount_kop / 100:.2f} ₽ — {p.created_at:%m-%d %H:%M}"
             for p in rows]
    await cq.answer()
    await cq.message.answer("💳 <b>Последние платежи</b>\n" + "\n".join(lines))


@router.callback_query(F.data == "adm:bc", IsAdmin())
async def bc_ask(cq: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_text)
    await cq.answer()
    await cq.message.answer("Текст рассылки. Уйдёт всем с подписью «Служебное уведомление».")


@router.message(AdminStates.broadcast_text, IsAdmin())
async def bc_text(m: Message, state: FSMContext):
    await state.update_data(bc=m.text)
    await m.answer("Отправить это всем?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="adm:bc_yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="adm:bc_no")],
    ]))


@router.callback_query(F.data == "adm:bc_yes", IsAdmin())
async def bc_yes(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await cq.answer("Рассылаю…")
    n = await send_broadcast(cq.bot, data.get("bc", ""))
    await cq.message.answer(f"Готово. Отправлено {n} пользователям.")


@router.callback_query(F.data == "adm:bc_no", IsAdmin())
async def bc_no(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.answer("Отменено")