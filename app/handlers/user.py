from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..repo import create_message, find_user, get_message, mark_read, upsert_user
from ..services.token import sign_token

router = Router()


class SendStates(StatesGroup):
    recipient = State()
    text = State()


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Отправить анонимное сообщение", callback_data="send")],
        [InlineKeyboardButton(text="ℹ️ Как это работает", callback_data="info")],
    ])


def anon_kb(msg_id: int, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply:{msg_id}")],
        [InlineKeyboardButton(text="👀 Узнать, кто написал",
                              url=f"{settings.landing_url}?t={token}")],
    ])


def consent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Разрешить", callback_data="sc:yes"),
        InlineKeyboardButton(text="🕶 Никогда", callback_data="sc:no"),
    ]])


WELCOME = (
    "👋 Это бот анонимных сообщений.\n\n"
    "Тебе может написать любой пользователь бота — и ты можешь написать любому, кто запустил бота.\n"
    "Отправитель остаётся анонимным, если сам не разрешит раскрытие."
)

INFO = (
    "ℹ️ Правила.\n"
    "• Отправить сообщение можно только тем, кто запустил бота.\n"
    "• При отправке ты выбираешь: разрешить ли раскрыть тебя, если получатель оплатит узнавание.\n"
    "• Оплата и раскрытие происходят на сайте; без твоего согласия ты остаёшься анонимным.\n"
    "• Напоминания о сообщениях приходят только если тебе действительно что-то отправили."
)


@router.message(CommandStart())
async def start(m: Message):
    await upsert_user(m.from_user)
    await m.answer(WELCOME, reply_markup=main_kb())


@router.callback_query(F.data == "info")
async def info(cq: CallbackQuery):
    await cq.answer()
    await cq.message.answer(INFO)


@router.callback_query(F.data == "send")
async def send_ask(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(SendStates.recipient)
    await cq.message.answer("Кому отправить? Пришли @username или числовой ID (пользователь должен был запустить бота).")


@router.message(SendStates.recipient)
async def send_recipient(m: Message, state: FSMContext):
    target = await find_user(m.text.strip())
    if target is None:
        return await m.answer("Этот пользователь ещё не активировал бота.")
    if target.id == m.from_user.id:
        return await m.answer("Себе отправить нельзя.")
    await state.update_data(recipient_id=target.id)
    await state.set_state(SendStates.text)
    await m.answer("Принял. Теперь текст сообщения.")


@router.message(SendStates.text)
async def send_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await m.answer(
        "Если получатель оплатит «узнать, кто написал» — разрешаешь раскрыть тебя?",
        reply_markup=consent_kb(),
    )


@router.callback_query(F.data.startswith("sc:"), SendStates.text)
async def send_consent(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    consent = cq.data == "sc:yes"
    msg = await create_message(cq.from_user.id, data["recipient_id"], data["text"], consent)
    token = sign_token({"m": msg.id, "s": cq.from_user.id, "u": data["recipient_id"],
                        "c": 1 if consent else 0})
    await cq.answer()
    await cq.message.answer("✅ Доставлено.")
    try:
        await cq.bot.send_message(
            data["recipient_id"],
            "📨 <b>Тебе пришло новое анонимное сообщение!</b>\n\n" + escape(data["text"]),
            reply_markup=anon_kb(msg.id, token),
        )
    except Exception:
        await cq.message.answer("Не удалось доставить (пользователь заблокировал бота?).")


@router.callback_query(F.data.startswith("reply:"))
async def reply(cq: CallbackQuery, state: FSMContext):
    msg = await get_message(int(cq.data.split(":")[1]))
    if msg is None or cq.from_user.id != msg.recipient_id:
        return await cq.answer("Недоступно", show_alert=True)
    await mark_read(msg.id)
    await state.update_data(recipient_id=msg.sender_id)
    await state.set_state(SendStates.text)
    await cq.answer()
    await cq.message.answer("Напиши ответ — собеседник получит его тоже анонимно.")