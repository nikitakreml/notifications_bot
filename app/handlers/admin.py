from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from app.db import (
    get_pending_users, approve_user, remove_pending, get_active_users,
    get_user_end_time, set_end_time, get_all_users,
    get_settings, toggle_setting, set_all_notifications,
)
from app.keyboards import (
    admin_menu_kb, approvals_keyboard_from_list, back_to_admin_menu_kb,
    admin_dashboard_kb, admin_notifications_kb,
    admin_set_picker_kb, back_to_set_list_kb,
)
from app.states import AddUserSG, SetEndSG, CheckUserSG, ApproveUserSG
from config import Config

router = Router()

PAGE_SIZE = 20

def _format_dashboard_page(
    users: list[tuple[int, str|None, str|None, bool, bool]],
    filter_mode: str,
    page: int,
) -> tuple[str, bool, bool, int, int]:
    total = len(users)
    with_date_cnt = sum(1 for _, __, et, ___, ____ in users if et)
    without_date_cnt = total - with_date_cnt

    if filter_mode == "with":
        users_f = [u for u in users if u[2]]
    elif filter_mode == "without":
        users_f = [u for u in users if not u[2]]
    else:
        users_f = list(users)

    users_f.sort(key=lambda u: (0 if u[2] else 1, u[2] or "9999-99-99 99:99:99"))

    total_pages = max(1, (len(users_f) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start, end = page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE
    page_slice = users_f[start:end]
    has_prev = page > 0
    has_next = page < (total_pages - 1)

    header = (
        "📊 <b>Дэшборд пользователей</b>\n"
        f"Всего: <b>{total}</b> | с датой: <b>{with_date_cnt}</b> | без даты: <b>{without_date_cnt}</b>\n"
        f"Стр. {page+1}/{total_pages} | Фильтр: <i>"
        f"{'все' if filter_mode=='all' else ('с датой' if filter_mode=='with' else 'без даты')}</i>\n"
    )
    if not page_slice:
        return header + "\n(нет записей для показа)", has_prev, has_next, page, total_pages

    lines = [
        "<pre>NAME                  UID        END_TIME            APPROVED ACTIVE",
        "-------------------------------------------------------------------"
    ]
    for uid, name, et, approved, active in page_slice:
        nm = (name or "—")[:20]
        et_disp = et if et else "—"
        appr = "✅" if approved else "❌"
        act = "🟢" if active else "⚪"
        lines.append(f"{nm:<20} {str(uid):<10} {et_disp:<19} {appr:^8} {act:^6}")
    lines.append("</pre>")
    text = header + "\n".join(lines)
    return text, has_prev, has_next, page, total_pages

# ----- back -----
@router.callback_query(F.data == "admin_back")
async def admin_back(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    await state.clear()
    try:
        await cb.message.edit_text("Меню администратора:", reply_markup=admin_menu_kb())
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await cb.answer()

# ----- dashboard -----
@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    users = await get_all_users()
    text, has_prev, has_next, page, _ = _format_dashboard_page(users, "all", 0)
    kb = admin_dashboard_kb("all", page, has_prev, has_next)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
    await cb.answer()

@router.callback_query(F.data.startswith("admin_dash:"))
async def admin_dashboard_page(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        _, filter_mode, page_str = cb.data.split(":", 2)
        page = int(page_str)
        if filter_mode not in {"all", "with", "without"}:
            filter_mode = "all"
    except Exception:
        filter_mode, page = "all", 0

    users = await get_all_users()
    text, has_prev, has_next, page, _ = _format_dashboard_page(users, filter_mode, page)
    kb = admin_dashboard_kb(filter_mode, page, has_prev, has_next)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            try:
                await cb.message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest:
                pass
        else:
            raise
    await cb.answer()

# ----- notifications (без изменений) -----
@router.callback_query(F.data == "admin_notifications")
async def admin_notifications(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    s = await get_settings()
    text = (
        "🔔 <b>Уведомления</b>\n"
        f"Все: {'<b>Вкл</b>' if s['master'] else '<b>Выкл</b>'}\n"
        f"−3 дня в 11:00: {'Вкл' if s['tminus3'] else 'Выкл'}\n"
        f"В день 11:00: {'Вкл' if s['onday'] else 'Выкл'}\n"
        f"После окончания (1ч): {'Вкл' if s['after'] else 'Выкл'}\n"
        "\nНажмите на пункт, чтобы переключить."
    )
    kb = admin_notifications_kb(s)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
    await cb.answer()

@router.callback_query(F.data.startswith("admin_notif_toggle:"))
async def admin_notifications_toggle(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    key = cb.data.split(":", 1)[1]
    s = await toggle_setting(key)
    text = (
        "🔔 <b>Уведомления</b>\n"
        f"Все: {'<b>Вкл</b>' if s['master'] else '<b>Выкл</b>'}\n"
        f"−3 дня в 11:00: {'Вкл' if s['tminus3'] else 'Выкл'}\n"
        f"В день 11:00: {'Вкл' if s['onday'] else 'Выкл'}\n"
        f"После окончания (1ч): {'Вкл' if s['after'] else 'Выкл'}\n"
    )
    kb = admin_notifications_kb(s)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            try:
                await cb.message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest:
                pass
        else:
            raise
    await cb.answer("Обновлено")

@router.callback_query(F.data.startswith("admin_notif_setall:"))
async def admin_notifications_setall(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    val = cb.data.split(":", 1)[1]
    s = await set_all_notifications(val == "on")
    text = (
        "🔔 <b>Уведомления</b>\n"
        f"Все: {'<b>Вкл</b>' if s['master'] else '<b>Выкл</b>'}\n"
        f"−3 дня в 11:00: {'Вкл' if s['tminus3'] else 'Выкл'}\n"
        f"В день 11:00: {'Вкл' if s['onday'] else 'Выкл'}\n"
        f"После окончания (1ч): {'Вкл' if s['after'] else 'Выкл'}\n"
    )
    kb = admin_notifications_kb(s)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
    await cb.answer("Готово")

# ----- заявки: теперь approve -> ввод имени -----
@router.callback_query(F.data == "admin_pending_list")
async def admin_pending_list(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    rows = await get_pending_users()
    if not rows:
        try:
            await cb.message.edit_text("Заявок на рассмотрение нет.", reply_markup=admin_menu_kb())
        except TelegramBadRequest:
            pass
        await cb.answer()
        return
    lines = [f"• {uid} — с {created_at}" for uid, created_at in rows]
    text = "Заявки на рассмотрение:\n" + "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=approvals_keyboard_from_list(rows))
    except TelegramBadRequest:
        pass
    await cb.answer()

@router.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve_ask_name(cb: types.CallbackQuery, state: FSMContext):
    """Шаг 1: спросить имя для указанного UID."""
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных.", show_alert=True)
        return

    await state.update_data(approve_uid=uid)
    await state.set_state(ApproveUserSG.name)
    await cb.message.edit_text(
        f"Введите <b>имя пользователя</b> для UID <b>{uid}</b>.\n"
        f"Например: <i>Иван Иванов</i>",
        reply_markup=back_to_admin_menu_kb()
    )
    await cb.answer()

@router.message(ApproveUserSG.name, F.text)
async def admin_approve_save_name(message: types.Message, state: FSMContext):
    """Шаг 2: сохранить имя и одобрить."""
    if message.from_user.id != Config.ADMIN_ID:
        return
    data = await state.get_data()
    uid = data.get("approve_uid")
    if not uid:
        await message.answer("Ошибка состояния. Откройте список заявок заново.", reply_markup=admin_menu_kb())
        await state.clear()
        return

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("❗ Слишком короткое имя. Введите корректное имя.",
                             reply_markup=back_to_admin_menu_kb())
        return

    await approve_user(int(uid), name)
    await remove_pending(int(uid))
    await state.clear()

    # уведомим пользователя
    try:
        await message.bot.send_message(int(uid), "✅ Ваша заявка одобрена. Добро пожаловать!")
        et = await get_user_end_time(int(uid))
        from app.keyboards import user_menu_kb
        await message.bot.send_message(int(uid), ("Доступ закрыт." if not et else f"Ваш доступ заканчивается: {et}"),
                                       reply_markup=user_menu_kb())
    except Exception:
        pass

    await message.answer(f"✅ Одобрено. Пользователь <b>{name}</b> (UID {uid}) сохранён.",
                         reply_markup=admin_menu_kb())

@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных.", show_alert=True)
        return
    await remove_pending(uid)
    try:
        await cb.bot.send_message(uid, "❌ Ваша заявка отклонена.")
    except Exception:
        pass
    await cb.answer("Пользователь отклонён.")
    rows = await get_pending_users()
    if rows:
        lines = [f"• {u} — с {ts}" for u, ts in rows]
        text = "Заявки на рассмотрение:\n" + "\n".join(lines)
        try:
            await cb.message.edit_text(text, reply_markup=approvals_keyboard_from_list(rows))
        except TelegramBadRequest:
            pass
    else:
        try:
            await cb.message.edit_text("Заявок на рассмотрение нет.", reply_markup=admin_menu_kb())
        except TelegramBadRequest:
            pass

# ----- список для установки даты (показываем имя) -----
@router.callback_query(F.data == "admin_set_end")
async def admin_set_end_open_list(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    users = await get_all_users()
    users.sort(key=lambda u: (0 if u[2] else 1, u[2] or "9999-99-99 99:99:99"))
    page = 0
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    items = [(uid, name, et) for uid, name, et, _appr, _act in users[0:PAGE_SIZE]]
    text = "⏱ <b>Выберите пользователя, чтобы установить дату окончания</b>"
    kb = admin_set_picker_kb(items, page, total_pages)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
    await state.clear()
    await cb.answer()

@router.callback_query(F.data.startswith("admin_set_list:"))
async def admin_set_end_paginate(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        page = int(cb.data.split(":", 1)[1])
    except Exception:
        page = 0

    users = await get_all_users()
    users.sort(key=lambda u: (0 if u[2] else 1, u[2] or "9999-99-99 99:99:99"))
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start, end = page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE
    items = [(uid, name, et) for uid, name, et, _appr, _act in users[start:end]]

    text = "⏱ <b>Выберите пользователя, чтобы установить дату окончания</b>"
    kb = admin_set_picker_kb(items, page, total_pages)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            try:
                await cb.message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest:
                pass
        else:
            raise
    await cb.answer()

@router.callback_query(F.data.startswith("admin_set_pick:"))
async def admin_set_end_pick_user(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        _p, uid_str, page_str = cb.data.split(":")
        uid = int(uid_str); page = int(page_str)
    except Exception:
        await cb.answer("Некорректные данные.", show_alert=True)
        return

    await state.update_data(user_id=uid, return_page=page)
    await state.set_state(SetEndSG.dt_str)
    await cb.message.edit_text(
        f"Введите дату и время для <b>{uid}</b> в формате: <code>YYYY-MM-DD HH:MM:SS</code>",
        reply_markup=back_to_set_list_kb(page)
    )
    await cb.answer()

@router.message(SetEndSG.dt_str, F.text)
async def admin_set_end_dt(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    data = await state.get_data()
    if not data or "user_id" not in data:
        await message.answer("Сначала выберите пользователя из списка.", reply_markup=admin_menu_kb())
        await state.clear()
        return
    uid = data["user_id"]; page = int(data.get("return_page", 0))
    dt_raw = message.text.strip()

    try:
        from datetime import datetime
        dt = datetime.strptime(dt_raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        await message.answer("❗ Неверный формат. Используйте: <code>YYYY-MM-DD HH:MM:SS</code>",
                             reply_markup=back_to_set_list_kb(page))
        return

    await set_end_time(uid, dt.strftime("%Y-%m-%d %H:%M:%S"))
    await message.answer(f"✅ Время окончания для <b>{uid}</b> установлено: <b>{dt}</b>")

    users = await get_all_users()
    users.sort(key=lambda u: (0 if u[2] else 1, u[2] or "9999-99-99 99:99:99"))
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start, end = page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE
    items = [(u, n, et) for u, n, et, _appr, _act in users[start:end]]

    text = "⏱ <b>Выберите пользователя, чтобы установить дату окончания</b>"
    kb = admin_set_picker_kb(items, page, total_pages)
    await message.answer(text, reply_markup=kb)
    await state.clear()

# ----- ручное добавление пользователя: user_id -> имя -----
@router.callback_query(F.data == "admin_add_user")
async def admin_add_user_btn(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    await state.set_state(AddUserSG.user_id)
    await cb.message.edit_text("Введите <b>user_id</b> пользователя (число).",
                               reply_markup=back_to_admin_menu_kb())
    await cb.answer()

@router.message(AddUserSG.user_id, F.text)
async def admin_add_user_id(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❗ Введите корректный целочисленный user_id.",
                             reply_markup=back_to_admin_menu_kb())
        return
    await state.update_data(user_id=uid)
    await state.set_state(AddUserSG.name)
    await message.answer("Теперь введите <b>имя пользователя</b> (например: Иван Иванов).",
                         reply_markup=back_to_admin_menu_kb())

@router.message(AddUserSG.name, F.text)
async def admin_add_user_name(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    data = await state.get_data()
    uid = data.get("user_id")
    if not uid:
        await message.answer("Сначала введите user_id.", reply_markup=back_to_admin_menu_kb())
        return

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("❗ Слишком короткое имя. Введите корректное имя.",
                             reply_markup=back_to_admin_menu_kb())
        return

    await approve_user(int(uid), name)   # одобряем с именем
    await remove_pending(int(uid))
    await state.clear()
    await message.answer(f"✅ Пользователь <b>{name}</b> (UID {uid}) добавлен/одобрен.",
                         reply_markup=admin_menu_kb())

# ----- прочее -----
@router.callback_query(F.data == "admin_list_active")
async def admin_list_active(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    rows = await get_active_users()
    text = "Активных пользователей нет." if not rows else \
        "Активные пользователи:\n" + "\n".join([f"• {uid} — до {et}" for uid, et in rows])
    try:
        await cb.message.edit_text(text, reply_markup=admin_menu_kb())
    except TelegramBadRequest:
        pass
    await cb.answer()

@router.callback_query(F.data == "admin_check_user")
async def admin_check_user(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    from app.states import CheckUserSG
    await state.set_state(CheckUserSG.user_id)
    await cb.message.edit_text("Введите user_id для проверки доступа.",
                               reply_markup=back_to_admin_menu_kb())
    await cb.answer()

@router.message(CheckUserSG.user_id, F.text)
async def admin_check_user_id(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    try:
        uid = int(message.text.strip())
        et = await get_user_end_time(uid)
        text = f"Пользователь {uid}: " + ("доступ закрыт" if not et else f"доступ до {et}")
        await message.answer(text, reply_markup=admin_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❗ Введите корректный целочисленный user_id.",
                             reply_markup=back_to_admin_menu_kb())
