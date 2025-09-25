# app/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def user_menu_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Проверить доступ", callback_data="user_check")
    return kb.as_markup()

def admin_menu_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Дэшборд", callback_data="admin_dashboard")
    kb.button(text="🔔 Уведомления", callback_data="admin_notifications")
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

def admin_dashboard_kb(filter_mode: str, page: int, has_prev: bool, has_next: bool) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # пагинация
    if has_prev:
        kb.button(text="◀️", callback_data=f"admin_dash:{filter_mode}:{page-1}")
    if has_next:
        kb.button(text="▶️", callback_data=f"admin_dash:{filter_mode}:{page+1}")
    if has_prev or has_next:
        kb.adjust(2)
    # фильтры
    kb.row(
        types.InlineKeyboardButton(text=("• Все" if filter_mode == "all" else "Все"),
                                   callback_data="admin_dash:all:0"),
        types.InlineKeyboardButton(text=("• С датой" if filter_mode == "with" else "С датой"),
                                   callback_data="admin_dash:with:0"),
        types.InlineKeyboardButton(text=("• Без даты" if filter_mode == "without" else "Без даты"),
                                   callback_data="admin_dash:without:0"),
    )
    # назад
    kb.row(types.InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_back"))
    return kb.as_markup()

def admin_notifications_kb(settings: dict) -> types.InlineKeyboardMarkup:
    def mark(b: bool) -> str: return "✅ Вкл" if b else "❌ Выкл"
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Все: {mark(settings['master'])}", callback_data="admin_notif_toggle:master")
    kb.button(text=f"−3 дня 11:00: {mark(settings['tminus3'])}", callback_data="admin_notif_toggle:tminus3")
    kb.button(text=f"В день 11:00: {mark(settings['onday'])}", callback_data="admin_notif_toggle:onday")
    kb.button(text=f"После окончания: {mark(settings['after'])}", callback_data="admin_notif_toggle:after")
    kb.adjust(1)
    kb.button(text="Включить всё", callback_data="admin_notif_setall:on")
    kb.button(text="Выключить всё", callback_data="admin_notif_setall:off")
    kb.adjust(2)
    kb.button(text="⬅️ В меню", callback_data="admin_back")
    return kb.as_markup()
