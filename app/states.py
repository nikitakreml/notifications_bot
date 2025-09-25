from aiogram.fsm.state import State, StatesGroup

class AddUserSG(StatesGroup):
    user_id = State()

class SetEndSG(StatesGroup):
    user_id = State()
    dt_str  = State()

class CheckUserSG(StatesGroup):
    user_id = State()
