from __future__ import annotations
import asyncio
import logging
from datetime import datetime, time
import os
from zoneinfo import ZoneInfo
from aiogram import Bot

from app.db import (
    get_settings,
    claim_tminus3_users,
    claim_onday_users,
    claim_after_expiry_users,
)

# Загружаем таймзону из переменной окружения TZ, с fallback на Europe/Berlin
try:
    TZ = ZoneInfo(os.getenv("TZ", "Europe/Berlin"))
except Exception:
    TZ = ZoneInfo("Europe/Berlin")

logger = logging.getLogger(__name__)


async def _notify_pre_expiry(bot: Bot):
    """
    Отправляет уведомления "за 3 дня" и "в день окончания" в 11:00.
    Работает идемпотентно, используя "claim-update" из db.py.
    """
    now_utc = datetime.utcnow()
    now_local = now_utc.astimezone(TZ)
    settings = await get_settings()
    if not settings.get("master"):
        return

    # Запускаем проверку только в небольшом окне после 11:00 по локальному времени.
    # Это предотвращает повторные отправки в ту же минуту и "догоняет" уведомления,
    # если бот был перезапущен ровно в 11:00.
    if now_local.time() >= time(11, 0) and now_local.time() < time(11, 5):
        # --- Уведомление за 3 дня ---
        if settings.get("tminus3"):
            users_to_notify = await claim_tminus3_users(now_utc, TZ)
            for user_id, end_time_str in users_to_notify:
                try:
                    end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                    await bot.send_message(
                        user_id,
                        f"⚠️ Напоминание\n\nВаш доступ истекает через 3 дня — {end_dt:%Y-%m-%d %H:%M}."
                    )
                except Exception:
                    logger.exception(f"Scheduler: T-3 notify failed for user_id: {user_id}")

        # --- Уведомление в день окончания ---
        if settings.get("onday"):
            users_to_notify = await claim_onday_users(now_utc, TZ)
            for user_id, end_time_str in users_to_notify:
                try:
                    end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                    await bot.send_message(
                        user_id,
                        f"⏳ Сегодня — последний день\n\nДоступ истекает сегодня в {end_dt:%H:%M} ({end_dt:%Y-%m-%d})."
                    )
                except Exception:
                    logger.exception(f"Scheduler: On-day notify failed for user_id: {user_id}")


async def _notify_after_expiry(bot: Bot):
    """
    Отправляет уведомление после истечения срока доступа.
    Работает идемпотентно и "догоняет" пропущенные уведомления в окне 65 минут.
    """
    now_utc = datetime.utcnow()
    settings = await get_settings()
    if not settings.get("master") or not settings.get("after"):
        return

    users_to_notify = await claim_after_expiry_users(now_utc)
    for user_id, end_time_str in users_to_notify:
        try:
            end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            await bot.send_message(
                user_id,
                f"❌ Доступ завершён\n\nСрок действия истёк: {end_dt:%Y-%m-%d %H:%M}."
            )
        except Exception:
            logger.exception(f"Scheduler: After-expiry notify failed for user_id: {user_id}")


async def loop(bot: Bot):
    """Основной цикл шедулера, запускается раз в минуту."""
    logger.info("Scheduler started successfully.")
    while True:
        try:
            await _notify_pre_expiry(bot)
            await _notify_after_expiry(bot)
        except Exception:
            # Логируем любую непредвиденную ошибку в цикле, чтобы он не остановился
            logger.exception("Scheduler loop encountered an unhandled error.")
        finally:
            # Тик раз в минуту
            await asyncio.sleep(60)


def start_scheduler(bot: Bot) -> asyncio.Task:
    """Создаёт и возвращает задачу для асинхронного запуска шедулера."""
    return asyncio.create_task(loop(bot))