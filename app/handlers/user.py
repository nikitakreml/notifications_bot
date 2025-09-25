from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.exceptions import TelegramBadRequest

from app.db import (
    add_pending, is_user_approved, get_user_end_time
)
from app.keyboards import user_menu_kb, approval_inline_kb, admin_menu_kb
from config import Config

router = Router()

@router.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id

    if user_id == Config.ADMIN_ID:
        await message.answer("Вы администратор. Выберите действие:", reply_markup=admin_menu_kb())
        return

    if await is_user_approved(user_id):
        end_time = await get_user_end_time(user_id)
        text = "Доступ закрыт." if not end_time else f"Ваш доступ заканчивается: {end_time}"
        await message.answer(text, reply_markup=user_menu_kb())
        return

    created = await add_pending(user_id)
    await message.answer(
        "📨 Ваша заявка отправлена администратору на рассмотрение.\n"
        "Вы получите уведомление после принятия решения."
    )

    if created:
        uname = ("@" + message.from_user.username) if message.from_user.username else "—"
        full_name = message.from_user.full_name or "—"
        text = (
            "🆕 Новая заявка на доступ\n"
            f"ID: {user_id}\n"
            f"Username: {uname}\n"
            f"Имя: {full_name}\n"
        )
        try:
            await message.bot.send_message(
                Config.ADMIN_ID,
                text,
                reply_markup=approval_inline_kb(user_id)
            )
        except Exception:
            pass

@router.message(StateFilter(None), F.text)
async def fallback_menu(message: types.Message):
    if message.from_user.id == Config.ADMIN_ID:
        await message.answer("Меню администратора:", reply_markup=admin_menu_kb())
    else:
        if not await is_user_approved(message.from_user.id):
            await message.answer("⏳ Ваша заявка на рассмотрении у администратора.")
            return
        await message.answer("Меню:", reply_markup=user_menu_kb())

@router.callback_query(F.data == "user_check")
async def user_check(cb: types.CallbackQuery):
    if not await is_user_approved(cb.from_user.id):
        await cb.answer("Ваша заявка ещё не одобрена.", show_alert=True)
        return
    end_time = await get_user_end_time(cb.from_user.id)
    text = "Доступ закрыт." if not end_time else f"Ваш доступ заканчивается: {end_time}"
    try:
        await cb.message.edit_text(text, reply_markup=user_menu_kb())
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await cb.answer()
