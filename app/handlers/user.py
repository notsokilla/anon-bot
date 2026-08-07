from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..repo import (
    create_message,
    create_offline_message,
    find_user,
    get_message,
    get_undelivered_messages,
    mark_read,
    upsert_user,
)
from ..services.token import sign_token

router = Router()


class SendStates(StatesGroup):
    recipient = State()
    text = State()


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Получать анонимные сообщения", callback_data="receive")],
        [InlineKeyboardButton(text="✉️ Отправить анонимное сообщение", callback_data="send")],
        [InlineKeyboardButton(text="❓ Как получать анонимные сообщения?", callback_data="howto")],
    ])


def anon_kb(msg_id: int, token: str) -> InlineKeyboardMarkup:
    """Клавиатура под анонимным сообщением для получателя."""
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
    "Тебе может написать любой пользователь — и ты можешь написать любому.\n"
    "Отправитель остаётся анонимным."
)

HOWTO_TEXT = (
    "💌 Начните получать анонимные сообщения прямо сейчас!\n\n"
    "🔗 Ваша ссылка: https://t.me/{bot_username}?start={user_id}\n\n"
    "💬 Поделитесь этой ссылкой в истории или в описании профиля, чтобы начать получать анонимные сообщения"
)

SEND_ASK_TEXT = (
    "💬 Отправить анонимное сообщение\n\n"
    "Отправьте анонимное сообщение ЛЮБОМУ человеку, даже если его нет в боте!\n"
    "Выберите пользователя с помощью кнопки ниже и помните — всё анонимно 👇"
)

SEND_TEXT_INSTRUCTION = (
    "✍️ Напишите сюда всё, что хотите ему передать, и когда он зайдет в бота, он увидит ваше сообщение, но не будет знать от кого оно\n\n"
    "Отправить можно: 📝 текст, 🎞 фото или видео, 🔊 кружки и голосовые, а также стикеры ✨"
)


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await upsert_user(m.from_user)
    
    # Обработка параметра start (реферальная ссылка или прямой переход к отправке сообщения)
    args = m.text.split() if m.text else []
    ref = None
    target_id = None
    
    for arg in args:
        if arg.startswith("ref="):
            ref = arg.split("=", 1)[1]
        elif arg.isdigit():
            target_id = int(arg)
    
    welcome_text = WELCOME
    
    # Если это реферальная ссылка
    if ref:
        welcome_text += f"\n\n🔗 Вы перешли по реферальной ссылке: {ref}"
        await m.answer(welcome_text, reply_markup=main_kb())
        return
    
    # Если это прямая ссылка на отправку сообщения конкретному пользователю
    if target_id and target_id != m.from_user.id:
        await m.answer(
            f"✍️ Вы хотите отправить анонимное сообщение пользователю с ID {target_id}\n\n"
            "Напишите ваше сообщение здесь:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_send")],
            ])
        )
        # Сохраняем получателя в состоянии
        await state.set_state(SendStates.text)
        await state.update_data(recipient_id=target_id, direct_link=True)
        return
    
    # Проверяем наличие офлайн-сообщений для пользователя
    offline_msgs = await get_undelivered_messages(m.from_user.id)
    if offline_msgs:
        welcome_text += f"\n\n📬 У вас есть {len(offline_msgs)} непрочитанных сообщений!"
        await m.answer(welcome_text, reply_markup=main_kb())
        
        # Отправляем все офлайн-сообщения
        for msg in offline_msgs:
            try:
                # Создаем обычное сообщение в БД
                anon_msg = await create_message(msg.sender_id, m.from_user.id, msg.content, False)
                await m.bot.send_message(
                    m.from_user.id,
                    f"📨 <b>Тебе пришло новое анонимное сообщение!</b>\n\n{escape(msg.content)}",
                    reply_markup=anon_kb(anon_msg.id, sign_token({"m": anon_msg.id, "s": msg.sender_id, "u": m.from_user.id, "c": 0})),
                )
                # Отмечаем как доставленное
                await mark_offline_message_delivered(msg.id)
            except Exception as e:
                pass  # Пользователь мог заблокировать бота
    else:
        await m.answer(welcome_text, reply_markup=main_kb())


@router.callback_query(F.data == "howto")
async def howto(cq: CallbackQuery):
    await cq.answer()
    link = f"https://t.me/{(await cq.bot.get_me()).username}?start={cq.from_user.id}"
    text = HOWTO_TEXT.format(bot_username=(await cq.bot.get_me()).username, user_id=cq.from_user.id)
    await cq.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Выложить в историю", url=f"tg://resolve?domain={cq.from_user.username or ''}")],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=link)],
    ]))


@router.callback_query(F.data == "receive")
async def receive(cq: CallbackQuery):
    await cq.answer()
    link = f"https://t.me/{(await cq.bot.get_me()).username}?start={cq.from_user.id}"
    text = (
        "💌 Начните получать анонимные сообщения прямо сейчас!\n\n"
        f"🔗 Ваша ссылка: {link}\n\n"
        "💬 Поделитесь этой ссылкой в истории или в описании профиля, чтобы начать получать анонимные сообщения"
    )
    await cq.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Выложить в историю", switch_inline_query="")],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=link)],
    ]))


@router.callback_query(F.data == "send")
async def send_ask(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(SendStates.recipient)
    await cq.message.answer(SEND_ASK_TEXT, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Выбрать пользователя", switch_inline_query="")],
    ]))


@router.message(SendStates.recipient)
async def send_recipient(m: Message, state: FSMContext):
    target = await find_user(m.text.strip())
    if target is None:
        return await m.answer("Этот пользователь ещё не активировал бота. Попробуйте отправить ему ссылку на бота.")
    if target.id == m.from_user.id:
        return await m.answer("Себе отправить нельзя.")
    await state.update_data(recipient_id=target.id)
    await state.set_state(SendStates.text)
    await m.answer(SEND_TEXT_INSTRUCTION, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_send")],
    ]))


@router.message(SendStates.text)
async def send_text(m: Message, state: FSMContext):
    data = await state.get_data()
    recipient_id = data.get("recipient_id")
    
    if not recipient_id:
        return await m.answer("Ошибка: получатель не указан. Начните сначала.")
    
    text = m.text or m.caption or ""
    file_id = None
    content_type = "text"
    
    # Определяем тип контента и извлекаем file_id если есть
    if m.photo:
        file_id = m.photo[-1].file_id
        content_type = "photo"
    elif m.video:
        file_id = m.video.file_id
        content_type = "video"
    elif m.voice:
        file_id = m.voice.file_id
        content_type = "voice"
    elif m.video_note:
        file_id = m.video_note.file_id
        content_type = "video_note"
    elif m.sticker:
        file_id = m.sticker.file_id
        content_type = "sticker"
    
    # Проверяем, есть ли получатель в боте
    target_user = await find_user(str(recipient_id))
    
    if target_user:
        # Получатель есть в боте - отправляем сразу
        msg = await create_message(m.from_user.id, recipient_id, text, False)
        await state.clear()
        
        await m.answer("✅ Доставлено.")
        
        # Отправляем сообщение получателю
        try:
            if content_type == "text":
                await m.bot.send_message(
                    recipient_id,
                    f"📨 <b>Тебе пришло новое анонимное сообщение!</b>\n\n{escape(text)}",
                    reply_markup=anon_kb(msg.id, sign_token({"m": msg.id, "s": m.from_user.id, "u": recipient_id, "c": 0})),
                )
            elif content_type == "sticker":
                await m.bot.send_sticker(
                    recipient_id,
                    sticker=file_id,
                    reply_markup=anon_kb(msg.id, sign_token({"m": msg.id, "s": m.from_user.id, "u": recipient_id, "c": 0})),
                )
            else:
                # Отправляем медиа-контент с caption
                send_methods = {
                    "photo": m.bot.send_photo,
                    "video": m.bot.send_video,
                    "voice": m.bot.send_voice,
                    "video_note": m.bot.send_video_note,
                }
                caption = f"📨 <b>Тебе пришло новое анонимное {content_type}!</b>"
                if text:
                    caption += f"\n\n{escape(text)}"
                await send_methods[content_type](
                    recipient_id,
                    file_id=file_id,
                    caption=caption,
                    reply_markup=anon_kb(msg.id, sign_token({"m": msg.id, "s": m.from_user.id, "u": recipient_id, "c": 0})),
                )
        except Exception as e:
            pass  # Пользователь мог заблокировать бота
    else:
        # Получателя нет в боте - сохраняем как офлайн-сообщение
        full_content = text if content_type == "text" else f"[{content_type}] {text}"
        await create_offline_message(m.from_user.id, recipient_id, full_content, content_type)
        await state.clear()
        
        await m.answer(
            "✅ Сообщение сохранено!\n\n"
            "Пользователь ещё не активировал бота. Как только он зайдет в бота, он получит ваше сообщение."
        )


@router.callback_query(F.data == "cancel_send")
async def cancel_send(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.answer("Отменено.")
    try:
        await cq.message.delete()
    except Exception:
        pass


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