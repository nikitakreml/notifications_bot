from aiogram.fsm.state import State, StatesGroup

class AddUserSG(StatesGroup):
    user_id = State()
    name    = State()   # <-- новое

class ApproveUserSG(StatesGroup):
    name = State()      # <-- новое: ввод имени при approve из заявок

class SetEndSG(StatesGroup):
    user_id = State()
    dt_str  = State()

class CheckUserSG(StatesGroup):
    user_id = State()
