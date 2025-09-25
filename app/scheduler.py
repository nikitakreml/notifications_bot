from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.db import (
    get_active_users_with_flags,
    mark_flag,
    update_active_status,
)

# Базовая тайм-зона (из требования): Europe/Berlin
TZ = ZoneInfo("Europe/Berlin")

def _parse_local_berlin(end_time_str: str) -> datetime | None:
    try:
        # храним локальное время без таймзоны -> трактуем как Europe/Berlin
        naive = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=TZ)
    except Exception:
        return None

async def _notify_pre_expiry(bot: Bot):
    """
    Ровно два уведомления:
      - за 3 дня в 11:00
      - в день окончания в 11:00
    Отправляется один раз (по флагам).
    """
    now = datetime.now(TZ)
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
        if not tminus3_sent and today == (end_date - timedelta(days=3)) and now.hour == 11:
            await bot.send_message(user_id, "⏰ Напоминание: через 3 дня в это же время доступ закончится.")
            await mark_flag(user_id, "tminus3_sent", True)

        # в день окончания в 11:00
        if not onday_sent and today == end_date and now.hour == 11:
            await bot.send_message(user_id, "⏰ Сегодня день окончания доступа. Проверьте продление.")
            await mark_flag(user_id, "onday_sent", True)

async def _notify_after_expiry(bot: Bot):
    """
    Одно уведомление в течение часа после окончания.
    Как только пришло — деактивируем пользователя.
    """
    now = datetime.now(TZ)
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
    """
    Простой устойчивый цикл:
    - каждую минуту проверяем условия.
    - точные «11:00» обеспечиваются тем, что код выполнится в интервале 11:00–11:59;
      при желании можно снизить sleep до 10–15 сек.
    """
    while True:
        try:
            await _notify_pre_expiry(bot)
            await _notify_after_expiry(bot)
        except Exception:
            # не валим цикл из-за единичной ошибки
            pass
        await asyncio.sleep(60)

def start_scheduler(bot: Bot) -> asyncio.Task:
    """Запускает цикл уведомлений, возвращает task."""
    return asyncio.create_task(loop(bot))
