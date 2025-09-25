from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def user_menu_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Проверить доступ", callback_data="user_check")
    return kb.as_markup()

def admin_menu_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Дэшборд", callback_data="admin_dashboard")           # <-- НОВОЕ
    kb.button(text="🗂 Заявки на рассмотрение", callback_data="admin_pending_list")
    kb.button(text="➕ Добавить пользователя", callback_data="admin_add_user")
    kb.button(text="⏱ Установить дату окончания", callback_data="admin_set_end")
    kb.button(text="🟢 Активные пользователи", callback_data="admin_list_active")
    kb.button(text="🔎 Проверить доступ пользователя", callback_data="admin_check_user")
    kb.adjust(1)
    return kb.as_markup()

def back_to_admin_menu_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад в меню", callback_data="admin_back")
    return kb.as_markup()

def approval_inline_kb(uid: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Принять {uid}", callback_data=f"admin_approve:{uid}")
    kb.button(text=f"🚫 Отклонить {uid}", callback_data=f"admin_reject:{uid}")
    kb.button(text="⬅️ В меню", callback_data="admin_back")
    kb.adjust(2, 1)
    return kb.as_markup()

def approvals_keyboard_from_list(pending: list[tuple[int, str]]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for uid, _ in pending:
        kb.button(text=f"✅ {uid}", callback_data=f"admin_approve:{uid}")
        kb.button(text=f"🚫 {uid}", callback_data=f"admin_reject:{uid}")
    kb.button(text="⬅️ В меню", callback_data="admin_back")
    kb.adjust(2, 1)
    return kb.as_markup()

# ---------- Клавиатура для дэшборда ----------
def admin_dashboard_kb(filter_mode: str, page: int, has_prev: bool, has_next: bool) -> types.InlineKeyboardMarkup:
    """
    filter_mode: 'all' | 'with' | 'without'
    page: номер страницы (0+)
    """
    caption = {
        "all": "• Все",
        "with": "• С датой" if filter_mode == "with" else "С датой",
        "without": "• Без даты" if filter_mode == "without" else "Без даты",
    }
    kb = InlineKeyboardBuilder()

    # Пагинация
    if has_prev:
        kb.button(text="◀️", callback_data=f"admin_dash:{filter_mode}:{page-1}")
    if has_next:
        kb.button(text="▶️", callback_data=f"admin_dash:{filter_mode}:{page+1}")
    if has_prev or has_next:
        kb.adjust(2)

    # Фильтры (выбранный помечаем точкой)
    kb.row(
        types.InlineKeyboardButton(text=("• Все" if filter_mode == "all" else "Все"),
                                   callback_data="admin_dash:all:0"),
        types.InlineKeyboardButton(text=("• С датой" if filter_mode == "with" else "С датой"),
                                   callback_data="admin_dash:with:0"),
        types.InlineKeyboardButton(text=("• Без даты" if filter_mode == "without" else "Без даты"),
                                   callback_data="admin_dash:without:0"),
    )

    # Назад
    kb.row(types.InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_back"))

    return kb.as_markup()
