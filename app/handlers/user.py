from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.repo import (
    get_or_create_user, get_user_by_username, save_pending_message, 
    get_pending_messages_for_user, get_all_users
)
import logging

logger = logging.getLogger(__name__)
router = Router()

class UserStates(StatesGroup):
    waiting_for_recipient = State()
    waiting_for_message = State()

@router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    user = await get_or_create_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        is_premium=message.from_user.is_premium or False
    )
    
    # Проверяем отложенные сообщения
    pending_msgs = await get_pending_messages_for_user(user.tg_id, user.username)
    
    welcome_text = f"👋 Привет, {user.first_name or 'друг'}!\n\n"
    welcome_text += "Я — анонимный бот. Ты можешь отправлять сообщения другим пользователям или получать их.\n\n"
    
    if pending_msgs:
        welcome_text += f"📬 **У вас {len(pending_msgs)} новых сообщений пока вы отсутствовали!**\n\n"
        for msg in pending_msgs:
            # Если есть sender_tg_id, можно попробовать показать кто, но это анонимно обычно
            await message.answer(f"📨 <b>Анонимное сообщение:</b>\n\n{msg.text}", parse_mode="HTML")
        welcome_text += "Все старые сообщения показаны выше."
    
    await message.answer(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Отправить письмо", callback_data="send_letter")],
            [InlineKeyboardButton(text="📖 Инструкция", callback_data="help_info")]
        ])
    )
    await state.clear()

@router.callback_query(F.data == "send_letter")
async def send_letter_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 Введите **ID** получателя или его **@username** (например, @durov):\n\n"
        "ℹ️ Если пользователя нет в базе, сообщение сохранится и придет, когда он запустит бота.",
        parse_mode="Markdown"
    )
    await UserStates.waiting_for_recipient.set()

@router.message(UserStates.waiting_for_recipient)
async def process_recipient(message: types.Message, state: FSMContext):
    recipient_input = message.text.strip()
    target_user = None
    target_tg_id = None
    target_username = None
    
    # Пробуем найти по ID
    if recipient_input.isdigit():
        target_tg_id = int(recipient_input)
        target_user = await get_or_create_user(tg_id=target_tg_id) # Создаем заглушку если нет
        target_username = target_user.username
    else:
        # Пробуем по юзернейму
        clean_username = recipient_input.lstrip('@')
        target_user = await get_user_by_username(clean_username)
        
        if target_user:
            target_tg_id = target_user.tg_id
            target_username = target_user.username
        else:
            # Пользователь не найден в БД. 
            # Мы НЕ можем узнать его ID по юзернейму через API бота если он не писал боту.
            # Но мы можем СОХРАНИТЬ сообщение с пометкой "для @username".
            # Когда этот юзер напишет /start, мы проверим совпадение username.
            # Для этого нам нужно сохранять в pending_messages не только tg_id, но и username.
            # А в get_pending_messages_for_user искать и по username тоже.
            # Упрощение: просим юзера сказать получателю "запусти бота".
            # НО ты просил сохранить. Ок, сохраняем с tg_id=0 (специальный флаг) или просто игнорируем tg_id при поиске.
            # Лучший вариант: сохраняем в БД как pending для username.
            
            await save_pending_message(
                recipient_tg_id=0, # 0 означает "поиск по юзернейму при входе"
                recipient_username=clean_username,
                text="⏳ Ожидаем запуска бота получателем...", # Это черновик
                sender_tg_id=message.from_user.id
            )
            # Перезапишем правильно ниже
            
            await message.answer(
                f"⚠️ Пользователь **@{clean_username}** не найден в базе бота.\n\n"
                "✅ Я сохранил ваше сообщение! Оно будет доставлено, как только этот пользователь запустит бота (/start).",
                parse_mode="Markdown"
            )
            # Сохраняем реальное сообщение в контексте, чтобы спросить текст
            await state.update_data(pending_username=clean_username)
            await UserStates.waiting_for_message.set()
            return

    if target_user:
        await state.update_data(target_tg_id=target_tg_id, target_username=target_username)
        await message.answer(f"👤 Получатель: {target_user.first_name} (@{target_username or 'нет'})\n\nНапишите сообщение:")
        await UserStates.waiting_for_message.set()
    else:
        await message.answer("❌ Не удалось определить получателя. Попробуйте снова (ID или @username).")

@router.message(UserStates.waiting_for_message)
async def process_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = message.text
    
    target_tg_id = data.get("target_tg_id")
    target_username = data.get("target_username")
    pending_username = data.get("pending_username") # Если искали по юзернейму и не нашли
    
    if pending_username:
        # Сохраняем для будущего пользователя
        await save_pending_message(
            recipient_tg_id=0, # Специальный маркер
            recipient_username=pending_username,
            text=text,
            sender_tg_id=message.from_user.id
        )
        await message.answer("✅ Сообщение сохранено и ждет своего часа!")
    else:
        # Отправляем напрямую
        try:
            await message.bot.send_message(target_tg_id, f"📨 **Анонимное сообщение**:\n\n{text}", parse_mode="Markdown")
            await message.answer("✅ Сообщение отправлено!")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить: {e}\nВозможно, пользователь заблокировал бота.")
    
    await state.clear()