from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, time

from zoneinfo import ZoneInfo
from aiogram import Bot

from app.db import (
    get_active_users_with_flags,
    mark_flag,
    update_active_status,
    get_settings,
)

# Важно: время берём по Берлину (как и раньше)
TZ = ZoneInfo("Europe/Berlin")

logger = logging.getLogger(__name__)

# --- утилиты времени ---

WINDOW_MINUTES = 5  # окно "догонялки" после 11:00

def _parse_local_berlin(end_time_str: str):
    """Парсим TEXT 'YYYY-MM-DD HH:MM:SS' как локальное время Берлина."""
    try:
        naive = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=TZ)
    except Exception:
        return None

def _in_window(now: datetime, target: datetime, minutes: int = WINDOW_MINUTES) -> bool:
    """True, если now в интервале [target, target+minutes)."""
    delta = (now - target).total_seconds()
    return 0 <= delta < minutes * 60

def _at_11(dt: datetime) -> datetime:
    """11:00:00 того же дня в TZ."""
    return datetime.combine(dt.date(), time(11, 0), tzinfo=TZ)

# --- уведомления ---

async def _notify_pre_expiry(bot: Bot):
    """
    - За 3 дня @11:00 (с окном 5 минут)
    - В день @11:00 (если доступ ещё не истёк к 11:00)
    """
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

        # --- за 3 дня в 11:00 ---
        if settings["tminus3"] and not tminus3_sent:
            target_dt = _at_11(end_dt - timedelta(days=3))
            if _in_window(now, target_dt):
                try:
                    await bot.send_message(
                        user_id,
                        f"⚠️ Напоминание\n\nВаш доступ истекает через 3 дня — {end_dt:%Y-%m-%d %H:%M}."
                    )
                    await mark_flag(user_id, "tminus3_sent", True)
                except Exception:
                    logger.exception("t-3 notify failed for %s", user_id)

        # --- в день в 11:00 (если к 11 доступ ещё не истёк) ---
        if settings["onday"] and not onday_sent:
            target_dt = _at_11(end_dt)
            if _in_window(now, target_dt) and end_dt >= target_dt:
                try:
                    await bot.send_message(
                        user_id,
                        f"⏳ Сегодня — последний день\n\nДоступ истекает сегодня в {end_dt:%H:%M} ({end_dt:%Y-%m-%d})."
                    )
                    await mark_flag(user_id, "onday_sent", True)
                except Exception:
                    logger.exception("on-day notify failed for %s", user_id)

async def _notify_after_expiry(bot: Bot):
    """После окончания — однократно в течение часа после end_time."""
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

        # В течение часа после окончания (догоняет даже если бот "спал" и проснулся позже 11:00)
        if end_dt <= now <= end_dt + timedelta(hours=1):
            try:
                await bot.send_message(
                    user_id,
                    f"❌ Доступ завершён\n\nСрок действия истёк: {end_dt:%Y-%m-%d %H:%M}."
                )
                await mark_flag(user_id, "after_sent", True)
                await update_active_status(user_id, False)
            except Exception:
                logger.exception("after-expiry notify failed for %s", user_id)

# --- основной цикл ---

async def loop(bot: Bot):
    while True:
        try:
            await _notify_pre_expiry(bot)
            await _notify_after_expiry(bot)
        except Exception:
            logger.exception("scheduler loop error")
        finally:
            await asyncio.sleep(60)  # тик раз в минуту

def start_scheduler(bot: Bot) -> asyncio.Task:
    return asyncio.create_task(loop(bot))
