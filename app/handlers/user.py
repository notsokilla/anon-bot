from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.repo import get_or_create_user, save_message, get_unread_messages, mark_messages_read, add_pending_message, delete_pending_message
from app.states import UserStates
from app.config import settings

router = Router()

@router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    args = message.text.split()
    target_id = None
    
    # Проверка на наличие аргумента (ссылка вида /start=123456)
    if len(args) > 1:
        try:
            target_id = int(args[1])
        except ValueError:
            pass

    user = await get_or_create_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    if target_id:
        # Переход по ссылке для отправки сообщения конкретному человеку
        if target_id == message.from_user.id:
            await message.answer("Вы не можете отправить сообщение сами себе!")
            return
        
        # Проверяем, есть ли получатель в базе
        recipient = await get_or_create_user(tg_id=target_id) # Создаст если нет, но нам нужно знать был ли он
        
        # Логика: если пользователя нет в БД (только что создали), сохраняем в pending
        # Но get_or_create_user всегда возвращает объект. Нужно проверить, был ли он новым.
        # Упростим: сохраняем в pending, а при старте получателя проверяем pending.
        
        await state.set_state(UserStates.wait_anon_msg)
        await state.update_data(target_id=target_id)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Отмена", callback_data="cancel_send")
        
        await message.answer(
            f"✍️ Вы собираетесь отправить анонимное сообщение пользователю с ID: <code>{target_id}</code>.\n\n"
            "Напишите сообщение (текст, фото, голосовое, кружок, стикер):",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        return

    # Обычный старт
    builder = InlineKeyboardBuilder()
    builder.button(text="💌 Получить анонимное сообщение", callback_data="menu_receive")
    builder.button(text="✍️ Отправить анонимное сообщение", callback_data="menu_send")
    builder.button(text="❓ Как это работает?", callback_data="menu_help")
    builder.adjust(1, 1, 1)
    
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n"
        "Я бот для анонимных сообщений.\n\n"
        "Выбери действие:",
        reply_markup=builder.as_markup()
    )
    
    # Проверка отложенных сообщений при обычном старте
    from app.repo import engine, PendingMessage
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session_maker() as session:
        stmt = select(PendingMessage).where(PendingMessage.recipient_tg_id == message.from_user.id)
        result = await session.execute(stmt)
        pending_msgs = result.scalars().all()
        
        if pending_msgs:
            await message.answer(f"📨 Вам пришло {len(pending_msgs)} сообщений, пока вас не было!")
            for pm in pending_msgs:
                try:
                    if pm.content_type == "photo":
                        await message.answer_photo(photo=pm.content_file_id, caption=pm.content_text)
                    elif pm.content_type == "video":
                        await message.answer_video(video=pm.content_file_id, caption=pm.content_text)
                    elif pm.content_type == "voice":
                        await message.answer_voice(voice=pm.content_file_id, caption=pm.content_text)
                    elif pm.content_type == "video_note":
                        await message.answer_video_note(video_note=pm.content_file_id)
                    elif pm.content_type == "sticker":
                        await message.answer_sticker(sticker=pm.content_file_id)
                    else:
                        await message.answer(pm.content_text)
                    
                    # Сохраняем в историю и удаляем из pending
                    await save_message(
                        sender_id=pm.sender_tg_id,
                        recipient_id=message.from_user.id,
                        text=pm.content_text,
                        file_id=pm.content_file_id,
                        content_type=pm.content_type
                    )
                    await session.delete(pm)
                except Exception as e:
                    print(f"Error sending pending msg: {e}")
        await session.commit()

@router.callback_query(F.data == "menu_receive")
async def menu_receive(cq: types.CallbackQuery):
    bot_username = (await cq.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={cq.from_user.id}"
    
    builder = InlineKeyboardBuilder()
    # Кнопка "Скопировать" - показываем ссылку текстом для копирования
    builder.button(text="📋 Скопировать ссылку", callback_data=f"copy_link_{cq.from_user.id}")
    # Кнопка "Поделиться" - используем switch_inline_query для шеринга в любой чат
    builder.button(text="🚀 Поделиться", switch_inline_query=f"Отправь мне анонимное сообщение: {link}")
    
    builder.adjust(1, 1)
    
    await cq.message.edit_text(
        f"💌 <b>Ваша персональная ссылка:</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Нажмите 'Скопировать ссылку' чтобы получить её для копирования\n"
        "Или нажмите 'Поделиться в истории' чтобы поделиться ссылкой!",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "menu_send")
async def menu_send_start(cq: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.wait_target)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_send")
    await cq.message.edit_text(
        "✍️ <b>Отправить анонимное сообщение</b>\n\n"
        "Введите ID пользователя или перешлите сообщение от него (если бот знает ID):\n\n"
        "Или используйте ссылку вида: <code>t.me/bot?start=ID</code>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(UserStates.wait_target)
async def process_target(message: types.Message, state: FSMContext):
    target_input = message.text.strip()
    
    # Проверяем, это юзернейм (начинается с @) или ID
    if target_input.startswith('@'):
        username = target_input[1:]  # Убираем @
        
        from app.repo import engine, User
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker
        async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
        
        async with async_session_maker() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            recipient = result.scalar_one_or_none()
            
            if not recipient:
                await message.answer(f"❌ Пользователь @{username} не найден в базе бота.\nПопросите его сначала запустить бота.")
                return
            
            target_id = recipient.tg_id
    else:
        try:
            target_id = int(target_input)
        except ValueError:
            await message.answer("Пожалуйста, введите корректный ID пользователя или @username.")
            return
    
    if target_id == message.from_user.id:
        await message.answer("Нельзя отправить сообщение самому себе!")
        return
        
    await state.update_data(target_id=target_id)
    await state.set_state(UserStates.wait_anon_msg)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_send")
    
    await message.answer(
        f"Адресат: <code>{target_id}</code>\n"
        "Напишите сообщение (текст, фото, голосовое, кружок, стикер):",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(UserStates.wait_anon_msg, F.content_type.in_(['text', 'photo', 'video', 'voice', 'video_note', 'sticker']))
async def process_anon_msg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    
    text = message.text or message.caption or ""
    file_id = None
    content_type = "text"
    
    if message.photo:
        file_id = message.photo[-1].file_id
        content_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        content_type = "video"
    elif message.voice:
        file_id = message.voice.file_id
        content_type = "voice"
    elif message.video_note:
        file_id = message.video_note.file_id
        content_type = "video_note"
    elif message.sticker:
        file_id = message.sticker.file_id
        content_type = "sticker"

    # Проверяем, есть ли получатель в базе
    from app.repo import engine, User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == target_id)
        result = await session.execute(stmt)
        recipient = result.scalar_one_or_none()
        
        if recipient:
            # Пользователь есть в боте - отправляем сразу
            await save_message(
                sender_id=message.from_user.id,
                recipient_id=recipient.id,
                text=text,
                file_id=file_id,
                content_type=content_type
            )
            
            try:
                if content_type == "photo":
                    await message.bot.send_photo(recipient.tg_id, photo=file_id, caption="📨 Новое анонимное сообщение:\n\n" + (text or ""))
                elif content_type == "video":
                    await message.bot.send_video(recipient.tg_id, video=file_id, caption="📨 Новое анонимное сообщение:\n\n" + (text or ""))
                elif content_type == "voice":
                    await message.bot.send_voice(recipient.tg_id, voice=file_id, caption="📨 Новое анонимное сообщение:\n\n" + (text or ""))
                elif content_type == "video_note":
                    await message.bot.send_video_note(recipient.tg_id, video_note=file_id, caption="📨 Новое анонимное сообщение")
                elif content_type == "sticker":
                    await message.bot.send_sticker(recipient.tg_id, sticker=file_id)
                else:
                    await message.bot.send_message(recipient.tg_id, f"📨 Новое анонимное сообщение:\n\n{text}")
                
                await message.answer("✅ Сообщение отправлено!")
            except Exception as e:
                await message.answer(f"❌ Ошибка отправки: {e}. Возможно, пользователь заблокировал бота.")
        else:
            # Пользователя нет в боте - сохраняем в pending
            await add_pending_message(
                recipient_tg_id=target_id,
                sender_tg_id=message.from_user.id,
                text=text,
                file_id=file_id,
                content_type=content_type
            )
            await message.answer(
                "💾 Пользователь еще не запускал бота.\n"
                "Сообщение сохранено и будет доставлено, как только он напишет /start!"
            )
    
    await state.clear()

@router.callback_query(F.data == "cancel_send")
async def cancel_send(cq: types.CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="💌 Получить", callback_data="menu_receive")
    builder.button(text="✍️ Отправить", callback_data="menu_send")
    builder.button(text="❓ Как это работает?", callback_data="menu_help")
    builder.adjust(1, 1, 1)
    await cq.message.edit_text("Действие отменено. Главное меню:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "menu_help")
async def menu_help(cq: types.CallbackQuery):
    text = (
        "❓ <b>Как пользоваться ботом?</b>\n\n"
        "1️⃣ <b>Получать сообщения:</b>\n"
        "   Нажмите 'Получить', скопируйте ссылку и поставьте её в профиль Telegram или в сторис.\n"
        "   Когда кто-то перейдет и напишет вам – вы получите уведомление!\n\n"
        "2️⃣ <b>Отправлять сообщения:</b>\n"
        "   Нажмите 'Отправить', введите ID пользователя (или перейдите по его ссылке).\n"
        "   Напишите сообщение – оно уйдет анонимно!\n\n"
        "🔒 Полная анонимность гарантирована."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="start") # Вернет на главное через хендлер старта? Нет, лучше свое меню
    # Пересоздадим главное меню
    builder.button(text="🏠 Главное меню", callback_data="start") 
    # Нужен хендлер на callback start, который вернет меню. Или просто сделаем редирект.
    # Добавим простой хендлер ниже.
    
    await cq.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data == "start")
async def back_to_start(cq: types.CallbackQuery):
    # Дублируем логику старта для возврата в меню
    builder = InlineKeyboardBuilder()
    builder.button(text="💌 Получить анонимное сообщение", callback_data="menu_receive")
    builder.button(text="✍️ Отправить анонимное сообщение", callback_data="menu_send")
    builder.button(text="❓ Как это работает?", callback_data="menu_help")
    builder.adjust(1, 1, 1)
    
    await cq.message.edit_text(
        f"Привет, {cq.from_user.first_name}!\nВыбери действие:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("copy_link_"))
async def copy_link_handler(cq: types.CallbackQuery):
    bot_username = (await cq.bot.get_me()).username
    user_id = cq.from_user.id
    link = f"https://t.me/{bot_username}?start={user_id}"
    
    await cq.message.answer(
        f"📋 <b>Ваша ссылка для копирования:</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Нажмите на ссылку выше чтобы скопировать её!",
        parse_mode="HTML"
    )
    await cq.answer("Ссылка отправлена!", show_alert=False)


# Хендлер для inline режима (когда пользователь делится ссылкой через switch_inline_query)
@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    bot_username = (await inline_query.bot.get_me()).username
    user_id = inline_query.from_user.id
    link = f"https://t.me/{bot_username}?start={user_id}"
    
    results = [
        types.InlineQueryResultArticle(
            id="share_link",
            title="Отправить мне анонимное сообщение",
            description=f"Нажми чтобы отправить анонимное сообщение!",
            input_message_content=types.InputTextMessageContent(
                message_text=f"📨 Отправь мне анонимное сообщение по ссылке:\n{link}",
                parse_mode="HTML"
            ),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(text="💌 Написать анонимно", url=link)
                ]]
            )
        )
    ]
    
    await inline_query.answer(results, cache_time=60)

