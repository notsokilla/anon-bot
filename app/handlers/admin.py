from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.repo import stats, get_broadcast_templates, create_broadcast_template, update_broadcast_template, delete_broadcast_template, is_admin_session, create_admin_session, invalidate_admin_session
from app.config import settings
from app.states import AdminStates, TemplateStates
import asyncio

router = Router()

# --- Helper Functions ---
def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.button(text="📋 Шаблоны", callback_data="admin_templates")
    builder.button(text="🚪 Выйти", callback_data="admin_logout")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

async def send_broadcast_with_kb(bot, text: str, kb: InlineKeyboardMarkup = None):
    """Рассылка с кнопкой (используется в bc_yes)"""
    from app.repo import engine, User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session_maker() as session:
        stmt = select(User.tg_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()
    
    count = 0
    errors = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, reply_markup=kb)
            count += 1
        except Exception:
            errors += 1
        await asyncio.sleep(0.05) # Anti-spam
    return count, errors

# --- Commands ---
@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔐 Войти по паролю", callback_data="admin_login_pass")
    await message.answer("Введите пароль администратора:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_login_pass")
async def login_pass_start(cq: types.CallbackQuery, state: FSMContext):
    await cq.message.edit_text("Введите пароль:")
    await state.set_state(AdminStates.waiting_password)

@router.message(AdminStates.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    if message.text == settings.admin_password:
        await create_admin_session(message.from_user.id)
        await message.answer("✅ Доступ разрешен.", reply_markup=get_admin_kb())
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль.")

@router.callback_query(F.data == "admin_stats")
async def stats_h(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    s = await stats()
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"Пользователей: {s['users']}\n"
        f"Сообщений всего: {s['messages']}\n"
        f"Непрочитанных: {s['unread']}"
    )
    await cq.message.edit_text(text, reply_markup=get_admin_kb(), parse_mode="HTML")

# --- Broadcast Logic ---
@router.callback_query(F.data == "admin_broadcast")
async def broadcast_menu(cq: types.CallbackQuery, state: FSMContext):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Простая рассылка", callback_data="bc_simple_start")
    builder.button(text="💰 Рассылка с кнопкой", callback_data="bc_kb_start")
    builder.button(text="⬅️ Назад", callback_data="admin_main")
    builder.adjust(1, 1, 1)
    
    await cq.message.edit_text("Выберите тип рассылки:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_main")
async def admin_main(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    await cq.message.edit_text("Админ-панель:", reply_markup=get_admin_kb())

@router.callback_query(F.data == "bc_simple_start")
async def bc_simple_start(cq: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_text)
    await cq.message.edit_text("Отправьте текст рассылки (или фото с подписью):")

@router.message(AdminStates.broadcast_text, F.content_type.in_(['text', 'photo', 'video', 'voice', 'video_note', 'sticker']))
async def bc_simple_process(message: types.Message, state: FSMContext):
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

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отправить", callback_data="bc_yes_simple")
    builder.button(text="❌ Отмена", callback_data="admin_broadcast")
    builder.adjust(1, 1)
    
    # Сохраняем данные в state
    await state.update_data(bc_text=text, bc_file_id=file_id, bc_content_type=content_type)
    
    if file_id:
        await message.answer(f"Готово к отправке:\n\n{text}", reply_markup=builder.as_markup())
    else:
        await message.answer(f"Готово к отправке:\n\n{text}", reply_markup=builder.as_markup())
    await state.set_state(AdminStates.broadcast_confirm)

@router.callback_query(F.data == "bc_yes_simple")
async def bc_yes_simple(cq: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("bc_text", "")
    file_id = data.get("bc_file_id")
    content_type = data.get("bc_content_type", "text")
    
    await cq.message.edit_text("🚀 Запуск рассылки...")
    
    from app.repo import engine, User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session_maker() as session:
        stmt = select(User.tg_id)
        result = await session.execute(stmt)
        user_ids = result.scalars().all()
    
    count = 0
    for uid in user_ids:
        try:
            if content_type == "photo":
                await cq.bot.send_photo(uid, photo=file_id, caption=text)
            elif content_type == "video":
                await cq.bot.send_video(uid, video=file_id, caption=text)
            elif content_type == "voice":
                await cq.bot.send_voice(uid, voice=file_id, caption=text)
            elif content_type == "video_note":
                await cq.bot.send_video_note(uid, video_note=file_id)
            elif content_type == "sticker":
                await cq.bot.send_sticker(uid, sticker=file_id)
            else:
                await cq.bot.send_message(uid, text)
            count += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
        
    await cq.message.edit_text(f"✅ Рассылка завершена. Получателей: {count}")
    await state.clear()

# --- Templates Management ---
@router.callback_query(F.data == "admin_templates")
async def templates_menu(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    templates = await get_broadcast_templates()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать шаблон", callback_data="tmpl_create")
    
    for t in templates[:5]: # Показываем первые 5
        status = "🟢" if t.use_in_auto else "🔴"
        name = t.text[:20] + "..." if len(t.text) > 20 else t.text
        builder.button(text=f"{status} {name}", callback_data=f"tmpl_edit_{t.id}")
    
    builder.button(text="⬅️ Назад", callback_data="admin_main")
    builder.adjust(1, 1, 1)
    
    await cq.message.edit_text("📋 Управление шаблонами:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("tmpl_create"))
async def tmpl_create_start(cq: types.CallbackQuery, state: FSMContext):
    await state.set_state(TemplateStates.wait_text)
    await cq.message.edit_text("Отправьте текст шаблона (или фото с подписью):")

@router.message(TemplateStates.wait_text, F.content_type.in_(['text', 'photo']))
async def tmpl_save_text(message: types.Message, state: FSMContext):
    text = message.text or message.caption
    image_id = None
    if message.photo:
        image_id = message.photo[-1].file_id
    
    await state.update_data(tmpl_text=text, tmpl_image=image_id)
    await state.set_state(TemplateStates.wait_button)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, добавить кнопку", callback_data="btn_yes")
    builder.button(text="Нет, без кнопки", callback_data="btn_no")
    builder.adjust(1, 1)
    
    await message.answer("Добавить кнопку к этому шаблону?", reply_markup=builder.as_markup())

@router.callback_query(F.data.in_(['btn_yes', 'btn_no']))
async def tmpl_btn_choice(cq: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    has_btn = cq.data == "btn_yes"
    
    if has_btn:
        await state.set_state(TemplateStates.wait_btn_text)
        await cq.message.edit_text("Введите текст кнопки (например: 'Узнать кто'):")
    else:
        # Сохраняем без кнопки
        await create_broadcast_template(
            text=data['tmpl_text'],
            image_id=data.get('tmpl_image'),
            use_in_auto=False,
            has_button=False
        )
        await cq.message.edit_text("✅ Шаблон сохранен без кнопки.")
        await state.clear()
        # Возврат в меню
        await templates_menu(cq)

@router.message(TemplateStates.wait_btn_text)
async def tmpl_save_btn_text(message: types.Message, state: FSMContext):
    btn_text = message.text
    await state.update_data(tmpl_btn_text=btn_text)
    await state.set_state(TemplateStates.wait_auto)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Включить авто-рассылку", callback_data="auto_yes")
    builder.button(text="Выключить авто-рассылку", callback_data="auto_no")
    builder.adjust(1, 1)
    
    await message.answer("Использовать этот шаблон в автоматической рассылке?", reply_markup=builder.as_markup())

@router.callback_query(F.data.in_(['auto_yes', 'auto_no']))
async def tmpl_finish(cq: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    use_auto = cq.data == "auto_yes"
    
    await create_broadcast_template(
        text=data['tmpl_text'],
        image_id=data.get('tmpl_image'),
        use_in_auto=use_auto,
        has_button=True,
        button_text=data['tmpl_btn_text'],
        button_url=settings.landing_url
    )
    
    await cq.message.edit_text(f"✅ Шаблон создан!\nАвто-рассылка: {'ВКЛ' if use_auto else 'ВЫКЛ'}")
    await state.clear()
    # Небольшая задержка перед возвратом в меню, чтобы пользователь увидел сообщение
    await asyncio.sleep(1)
    await templates_menu(cq)
# --- Template Edit Handler ---
@router.callback_query(F.data.startswith("tmpl_edit_"))
async def tmpl_edit(cq: types.CallbackQuery, state: FSMContext):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    tmpl_id = int(cq.data.split("_")[-1])
    tmpl = await get_broadcast_template_by_id(tmpl_id)
    
    if not tmpl:
        return await cq.answer("Шаблон не найден", show_alert=True)
    
    status = "🟢 ВКЛ" if tmpl.use_in_auto else "🔴 ВЫКЛ"
    btn_info = f"🔘 Кнопка: {tmpl.button_text} -> {tmpl.button_url}" if tmpl.has_button else "❌ Без кнопки"
    
    text = (
        f"📋 <b>Редактирование шаблона #{tmpl.id}</b>\n\n"
        f"Текст:\n{tmpl.text}\n\n"
        f"{status} авто-рассылку\n"
        f"{btn_info}\n\n"
        f"Создан: {tmpl.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Переключить авто-рассылку", callback_data=f"tmpl_toggle_auto_{tmpl.id}")
    builder.button(text="✏️ Изменить текст", callback_data=f"tmpl_change_text_{tmpl.id}")
    builder.button(text="🗑 Удалить шаблон", callback_data=f"tmpl_delete_{tmpl.id}")
    builder.button(text="⬅️ Назад", callback_data="admin_templates")
    builder.adjust(1, 1, 1, 1)
    
    await cq.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("tmpl_toggle_auto_"))
async def tmpl_toggle_auto(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    tmpl_id = int(cq.data.split("_")[-1])
    tmpl = await get_broadcast_template_by_id(tmpl_id)
    
    if tmpl:
        await update_broadcast_template(tmpl_id, use_in_auto=not tmpl.use_in_auto)
        await cq.answer(f"Авто-рассылка {'включена' if not tmpl.use_in_auto else 'выключена'}", show_alert=True)
        await tmpl_edit(cq, None)  # Refresh the view

@router.callback_query(F.data.startswith("tmpl_delete_"))
async def tmpl_delete_confirm(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    tmpl_id = int(cq.data.split("_")[-1])
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"tmpl_delete_yes_{tmpl_id}")
    builder.button(text="❌ Отмена", callback_data=f"tmpl_edit_{tmpl_id}")
    builder.adjust(1, 1)
    
    await cq.message.edit_text("Вы уверены что хотите удалить этот шаблон?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("tmpl_delete_yes_"))
async def tmpl_delete_yes(cq: types.CallbackQuery):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    tmpl_id = int(cq.data.split("_")[-1])
    await delete_broadcast_template(tmpl_id)
    await cq.message.edit_text("✅ Шаблон удален")
    await asyncio.sleep(1)
    await templates_menu(cq)

@router.callback_query(F.data.startswith("tmpl_change_text_"))
async def tmpl_change_text_start(cq: types.CallbackQuery, state: FSMContext):
    if not await is_admin_session(cq.from_user.id):
        return await cq.answer("Сессия истекла", show_alert=True)
    
    tmpl_id = int(cq.data.split("_")[-1])
    await state.update_data(editing_tmpl_id=tmpl_id)
    await state.set_state(TemplateStates.wait_edit_text)
    await cq.message.edit_text("Отправьте новый текст для шаблона:")

@router.message(TemplateStates.wait_edit_text)
async def tmpl_save_new_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tmpl_id = data.get('editing_tmpl_id')
    
    if tmpl_id:
        await update_broadcast_template(tmpl_id, text=message.text)
        await message.answer("✅ Текст обновлен!")
        await state.clear()
        
        # Return to templates menu
        from aiogram.types import CallbackQuery
        # Can't directly call templates_menu, so just inform user
    else:
        await message.answer("❌ Ошибка: ID шаблона не найден")
        await state.clear()

@router.callback_query(F.data == "admin_logout")
async def admin_logout(cq: types.CallbackQuery):
    await invalidate_admin_session(cq.from_user.id)
    await cq.message.edit_text("✅ Вы вышли из админ-панели.")
