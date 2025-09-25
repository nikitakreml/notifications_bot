from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from app.db import (
    get_pending_users, approve_user, remove_pending, get_active_users,
    get_user_end_time, set_end_time, get_all_users
)
from app.keyboards import (
    admin_menu_kb, approvals_keyboard_from_list, back_to_admin_menu_kb,
    admin_dashboard_kb
)
from app.states import AddUserSG, SetEndSG, CheckUserSG
from config import Config

router = Router()

PAGE_SIZE = 20  # строк на страницу для дэшборда

def _format_dashboard_page(users: list[tuple[int, str|None, bool, bool]],
                           filter_mode: str, page: int) -> tuple[str, bool, bool, int, int]:
    """
    Возвращает (text, has_prev, has_next, page, total_pages)
    users: (user_id, end_time, approved, active)
    """
    # Счётчики (до фильтра)
    total = len(users)
    with_date_cnt = sum(1 for _, et, *_ in users if et)
    without_date_cnt = total - with_date_cnt

    # Фильтрация
    if filter_mode == "with":
        users_f = [u for u in users if u[1]]
    elif filter_mode == "without":
        users_f = [u for u in users if not u[1]]
    else:
        users_f = list(users)

    # Сортировка: сначала по наличию даты (без даты в конце), затем по дате
    def _sort_key(u):
        uid, et, *_ = u
        return (0 if et else 1, (et or "9999-99-99 99:99:99"))
    users_f.sort(key=_sort_key)

    # Пагинация
    total_pages = max(1, (len(users_f) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_slice = users_f[start:end]
    has_prev = page > 0
    has_next = page < (total_pages - 1)

    # Форматирование
    header = (
        "📊 <b>Дэшборд пользователей</b>\n"
        f"Всего: <b>{total}</b> | с датой: <b>{with_date_cnt}</b> | без даты: <b>{without_date_cnt}</b>\n"
        f"Стр. {page+1}/{total_pages} | Фильтр: <i>{'все' if filter_mode=='all' else ('с датой' if filter_mode=='with' else 'без даты')}</i>\n"
    )

    if not page_slice:
        return header + "\n(нет записей для показа)", has_prev, has_next, page, total_pages

    # Таблица моноширинным шрифтом
    lines = ["<pre>UID        END_TIME            APPROVED ACTIVE",
             "----------------------------------------------"]
    for uid, et, approved, active in page_slice:
        et_disp = et if et else "—"
        appr = "✅" if approved else "❌"
        act = "🟢" if active else "⚪"
        lines.append(f"{str(uid):<10} {et_disp:<19} {appr:^8} {act:^6}")
    lines.append("</pre>")

    text = header + "\n".join(lines)
    return text, has_prev, has_next, page, total_pages

# ===== Назад =====
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

# ===== Дэшборд: вход =====
@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    users = await get_all_users()
    text, has_prev, has_next, page, _ = _format_dashboard_page(users, filter_mode="all", page=0)
    kb = admin_dashboard_kb("all", page, has_prev, has_next)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        # если «message is not modified» — просто обновим клавиатуру
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass
    await cb.answer()

# ===== Дэшборд: пагинация/фильтры =====
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
            # попробуем хотя бы клавиатуру
            try:
                await cb.message.edit_reply_markup(reply_markup=kb)
            except TelegramBadRequest:
                pass
        else:
            raise
    await cb.answer()

# ===== Оставшиеся обработчики (заявки, approve/reject, FSM и пр.) ниже без изменений =====
# ... (оставь остальной файл таким, как у тебя сейчас после последних правок)

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
async def admin_approve(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Ошибка данных.", show_alert=True)
        return

    # ЯВНО одобряем
    await approve_user(uid)
    await remove_pending(uid)

    try:
        await cb.bot.send_message(uid, "✅ Ваша заявка одобрена. Добро пожаловать!")
        end_time = await get_user_end_time(uid)
        text = "Доступ закрыт." if not end_time else f"Ваш доступ заканчивается: {end_time}"
        from app.keyboards import user_menu_kb
        await cb.bot.send_message(uid, text, reply_markup=user_menu_kb())
    except Exception:
        pass

    await cb.answer("Пользователь одобрен.")
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

# ===== Добавить пользователя (FSM) =====
@router.callback_query(F.data == "admin_add_user")
async def admin_add_user_btn(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    await state.set_state(AddUserSG.user_id)
    await cb.message.edit_text("Введите user_id пользователя (число).", reply_markup=back_to_admin_menu_kb())
    await cb.answer()

@router.message(AddUserSG.user_id, F.text)
async def admin_add_user_id(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    try:
        uid = int(message.text.strip())
        await approve_user(uid)     # <- сразу одобряем
        await remove_pending(uid)
        await message.answer(f"✅ Пользователь {uid} добавлен/одобрен.", reply_markup=admin_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❗ Введите корректный целочисленный user_id.", reply_markup=back_to_admin_menu_kb())

# ===== Установить дату окончания (FSM) =====
@router.callback_query(F.data == "admin_set_end")
async def admin_set_end(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    await state.set_state(SetEndSG.user_id)
    await cb.message.edit_text("Введите user_id пользователя, для которого установить дату окончания.",
                               reply_markup=back_to_admin_menu_kb())
    await cb.answer()

@router.message(SetEndSG.user_id, F.text)
async def admin_set_end_user(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    try:
        uid = int(message.text.strip())
        await state.update_data(user_id=uid)
        await state.set_state(SetEndSG.dt_str)
        await message.answer("Введите дату и время в формате: YYYY-MM-DD HH:MM:SS",
                             reply_markup=back_to_admin_menu_kb())
    except ValueError:
        await message.answer("❗ Введите корректный целочисленный user_id.", reply_markup=back_to_admin_menu_kb())

@router.message(SetEndSG.dt_str, F.text)
async def admin_set_end_dt(message: types.Message, state: FSMContext):
    if message.from_user.id != Config.ADMIN_ID:
        return
    dt_raw = message.text.strip()
    try:
        from datetime import datetime
        dt = datetime.strptime(dt_raw, "%Y-%m-%d %H:%M:%S")
        data = await state.get_data()
        uid = data["user_id"]
        await set_end_time(uid, dt.strftime("%Y-%m-%d %H:%M:%S"))
        await message.answer(f"✅ Время окончания для {uid} установлено: {dt}", reply_markup=admin_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❗ Неверный формат. Используйте: YYYY-MM-DD HH:MM:SS",
                             reply_markup=back_to_admin_menu_kb())

@router.callback_query(F.data == "admin_list_active")
async def admin_list_active(cb: types.CallbackQuery):
    if cb.from_user.id != Config.ADMIN_ID:
        await cb.answer("Недостаточно прав.", show_alert=True)
        return
    rows = await get_active_users()
    if not rows:
        text = "Активных пользователей нет."
    else:
        lines = [f"• {uid} — до {et}" for uid, et in rows]
        text = "Активные пользователи:\n" + "\n".join(lines)
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
    await state.set_state(CheckUserSG.user_id)
    await cb.message.edit_text("Введите user_id для проверки доступа.", reply_markup=back_to_admin_menu_kb())
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
        await message.answer("❗ Введите корректный целочисленный user_id.", reply_markup=back_to_admin_menu_kb())
