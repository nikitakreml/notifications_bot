from aiogram.fsm.state import State, StatesGroup

class AddUserSG(StatesGroup):
    """Состояния для ручного добавления пользователя админом."""
    user_id = State()
    name = State()

class ApproveUserSG(StatesGroup):
    """Состояние для ввода имени при одобрении заявки."""
    name = State()

class SetEndSG(StatesGroup):
    """Состояния для установки даты окончания доступа."""
    user_id = State()
    dt_str = State()

class CheckUserSG(StatesGroup):
    """Состояние для проверки доступа конкретного пользователя."""
    user_id = State()