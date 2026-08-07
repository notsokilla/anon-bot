from aiogram.fsm.state import StatesGroup, State

class UserStates(StatesGroup):
    wait_target = State()
    wait_anon_msg = State()

class AdminStates(StatesGroup):
    waiting_password = State()
    broadcast_text = State()
    broadcast_confirm = State()

class TemplateStates(StatesGroup):
    wait_text = State()
    wait_button = State()
    wait_btn_text = State()
    wait_auto = State()
    wait_edit_text = State()