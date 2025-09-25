from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.db import (
    get_active_users_with_flags,
    mark_flag,
    update_active_status,
    get_settings,  # <-- НОВОЕ
)

TZ = ZoneInfo("Europe/Berlin")

def _parse_local_berlin(end_time_str: str):
    try:
        naive = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=TZ)
    except Exception:
        return None

async def _notify_pre_expiry(bot: Bot):
    now = datetime.now(TZ)
    settings = await get_settings()
    if not settings["master"]:
        return

    users = await get_active_users_with_flags()
    for user_id, end_time, tminus3_sent, onday_sent, _after_sent in users:
        if not end_time:
            continue
        end_dt = _parse_local_berlin(end_time)
        if not end_dt:
            continue

        end_date = end_dt.date()
        today = now.date()

        # за 3 дня в 11:00
        if settings["tminus3"] and not tminus3_sent and today == (end_date - timedelta(days=3)) and now.hour == 11:
            await bot.send_message(user_id, "⏰ Напоминание: через 3 дня в это же время доступ закончится.")
            await mark_flag(user_id, "tminus3_sent", True)

        # в день окончания в 11:00
        if settings["onday"] and not onday_sent and today == end_date and now.hour == 11:
            await bot.send_message(user_id, "⏰ Сегодня день окончания доступа. Проверьте продление.")
            await mark_flag(user_id, "onday_sent", True)

async def _notify_after_expiry(bot: Bot):
    now = datetime.now(TZ)
    settings = await get_settings()
    if not settings["master"] or not settings["after"]:
        return

    users = await get_active_users_with_flags()
    for user_id, end_time, _tminus3, _onday, after_sent in users:
        if after_sent or not end_time:
            continue
        end_dt = _parse_local_berlin(end_time)
        if not end_dt:
            continue

        if end_dt <= now <= end_dt + timedelta(hours=1):
            await bot.send_message(user_id, "❌ Доступ окончен.")
            await mark_flag(user_id, "after_sent", True)
            await update_active_status(user_id, False)

async def loop(bot: Bot):
    while True:
        try:
            await _notify_pre_expiry(bot)
            await _notify_after_expiry(bot)
        except Exception:
            pass
        await asyncio.sleep(60)

def start_scheduler(bot: Bot) -> asyncio.Task:
    return asyncio.create_task(loop(bot))
