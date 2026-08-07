from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.config import settings
from app.repo import (
    get_all_users, get_broadcast_templates, get_broadcast_template_by_id, 
    update_broadcast_template, add_broadcast_template
)
import logging

logger = logging.getLogger(__name__)
router = Router()

class AdminStates(StatesGroup):
    waiting_password = State()
    template_edit_name = State()
    template_edit_text = State()
    template_edit_cron = State()
    broadcast_select = State()
    manual_broadcast_text = State()

# --- Вход в админку ---

@router.message(Command("admin"))
async def admin_login_start(message: types.Message, state: FSMContext):
    await message.answer("🔐 Введите пароль администратора:")
    await state.set_state(AdminStates.waiting_password)

@router.message(AdminStates.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    if message.text == settings.admin_password:
        await message.answer("✅ Доступ разрешен. Выберите действие:", reply_markup=get_admin_menu())
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль.")
        await state.clear()

def get_admin_menu():
    kb = [
        [InlineKeyboardButton(text="📢 Рассылка по шаблону", callback_data="admin_broadcast_tpl")],
        [InlineKeyboardButton(text="✍️ Ручная рассылка (текст)", callback_data="admin_manual_broadcast")],
        [InlineKeyboardButton(text="📝 Редактор шаблонов", callback_data="admin_templates_list")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "admin_exit")
async def admin_exit(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👋 Вы вышли из панели администратора.")

# --- Управление шаблонами ---

@router.callback_query(F.data == "admin_templates_list")
async def templates_list(callback: types.CallbackQuery):
    templates = await get_broadcast_templates()
    if not templates:
        await callback.answer("Шаблонов нет.", show_alert=True)
        return
    
    text = "📝 **Список шаблонов:**\n\n"
    kb = []
    for t in templates:
        status = "🟢 ВКЛ" if t.is_active else "🔴 ВЫКЛ"
        text += f"ID: `{t.id}` | {status}\nНазвание: {t.name}\nКрон: `{t.cron_schedule or 'Нет'}`\n\n"
        kb.append([InlineKeyboardButton(text=f"✏️ {t.name}", callback_data=f"tmpl_edit_{t.id}")])
    
    kb.append([InlineKeyboardButton(text="➕ Создать новый", callback_data="tmpl_create_new")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_exit")])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("tmpl_edit_"))
async def tmpl_edit(callback: types.CallbackQuery, state: FSMContext):
    tmpl_id = int(callback.data.split("_")[-1])
    tmpl = await get_broadcast_template_by_id(tmpl_id)
    if not tmpl:
        await callback.answer("Шаблон не найден!", show_alert=True)
        return
    
    await state.update_data(tmpl_id=tmpl_id)
    
    text = (f"✏️ **Редактирование шаблона #{tmpl.id}**\n\n"
            f"Название: `{tmpl.name}`\n"
            f"Статус: {'🟢 ВКЛ' if tmpl.is_active else '🔴 ВЫКЛ'}\n"
            f"Крон: `{tmpl.cron_schedule or 'Нет'}`\n\n"
            f"Текст:\n{tmpl.text}")
    
    kb = [
        [InlineKeyboardButton(text="Изменить название", callback_data="tmpl_change_name")],
        [InlineKeyboardButton(text="Изменить текст", callback_data="tmpl_change_text")],
        [InlineKeyboardButton(text="Изменить крон", callback_data="tmpl_change_cron")],
        [InlineKeyboardButton(text="Переключить статус", callback_data=f"tmpl_toggle_status_{tmpl_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_templates_list")]
    ]
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "tmpl_change_name")
async def tmpl_change_name_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.template_edit_name)
    await callback.message.answer("Введите новое название шаблона:")

@router.message(AdminStates.template_edit_name)
async def tmpl_change_name_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tmpl_id = data.get("tmpl_id")
    await update_broadcast_template(tmpl_id, name=message.text)
    await message.answer("✅ Название обновлено. Вернитесь в меню шаблонов.")
    await state.clear()

@router.callback_query(F.data == "tmpl_change_text")
async def tmpl_change_text_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.template_edit_text)
    await callback.message.answer("Введите новый текст шаблона:")

@router.message(AdminStates.template_edit_text)
async def tmpl_change_text_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tmpl_id = data.get("tmpl_id")
    await update_broadcast_template(tmpl_id, text=message.text)
    await message.answer("✅ Текст обновлен. Вернитесь в меню шаблонов.")
    await state.clear()

@router.callback_query(F.data == "tmpl_change_cron")
async def tmpl_change_cron_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.template_edit_cron)
    await callback.message.answer("Введите расписание (cron: `мин час день месяц день_недели`) или `none` для отключения:")

@router.message(AdminStates.template_edit_cron)
async def tmpl_change_cron_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tmpl_id = data.get("tmpl_id")
    cron = message.text.strip()
    if cron.lower() == "none":
        cron = None
    await update_broadcast_template(tmpl_id, cron_schedule=cron)
    await message.answer(f"✅ Расписание обновлено: `{cron}`")
    await state.clear()

@router.callback_query(F.data.startswith("tmpl_toggle_status_"))
async def tmpl_toggle_status(callback: types.CallbackQuery):
    tmpl_id = int(callback.data.split("_")[-1])
    tmpl = await get_broadcast_template_by_id(tmpl_id)
    if tmpl:
        new_status = not tmpl.is_active
        await update_broadcast_template(tmpl_id, is_active=new_status)
        status_str = "включен" if new_status else "выключен"
        await callback.answer(f"Шаблон {status_str}", show_alert=True)
        # Просто обновляем текущее сообщение с новым статусом (костыль, но работает)
        await tmpl_edit(callback, None) 

# --- Ручная рассылка ---

@router.callback_query(F.data == "admin_manual_broadcast")
async def manual_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.manual_broadcast_text)
    await callback.message.answer("✍️ Отправьте текст сообщения для рассылки всем пользователям:")

@router.message(AdminStates.manual_broadcast_text)
async def manual_broadcast_process(message: types.Message, state: FSMContext):
    users = await get_all_users()
    count = 0
    text = message.text
    for user in users:
        try:
            await message.bot.send_message(user.tg_id, text)
            count += 1
        except Exception as e:
            logger.error(f"Не удалось отправить пользователю {user.tg_id}: {e}")
    
    await message.answer(f"✅ Рассылка завершена. Отправлено: {count}/{len(users)}")
    await state.clear()

@router.callback_query(F.data == "admin_broadcast_tpl")
async def broadcast_tpl_start(callback: types.CallbackQuery, state: FSMContext):
    templates = await get_broadcast_templates()
    if not templates:
        await callback.answer("Нет активных шаблонов!", show_alert=True)
        return
    
    kb = []
    active_found = False
    for t in templates:
        if t.is_active:
            kb.append([InlineKeyboardButton(text=t.name, callback_data=f"send_tpl_{t.id}")])
            active_found = True
            
    if not active_found:
        await callback.answer("Нет активных шаблонов для отправки!", show_alert=True)
        return

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_exit")])
    
    await callback.message.edit_text("Выберите шаблон для отправки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AdminStates.broadcast_select)

@router.callback_query(F.data.startswith("send_tpl_"))
async def send_tpl_process(callback: types.CallbackQuery, state: FSMContext):
    tmpl_id = int(callback.data.split("_")[-1])
    tmpl = await get_broadcast_template_by_id(tmpl_id)
    if not tmpl:
        await callback.answer("Шаблон не найден!", show_alert=True)
        return
    
    users = await get_all_users()
    count = 0
    for user in users:
        try:
            await callback.bot.send_message(user.tg_id, tmpl.text)
            count += 1
        except Exception as e:
            logger.error(f"Ошибка рассылки {user.tg_id}: {e}")
            
    await callback.message.answer(f"✅ Рассылка шаблона '{tmpl.name}' завершена. Отправлено: {count}/{len(users)}")
    await state.clear()