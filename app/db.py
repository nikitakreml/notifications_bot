from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import logging
from sqlalchemy import Column, Integer, String, Boolean, select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy.orm import declarative_base, sessionmaker
import asyncio
import contextlib
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "data/bot.db"))
Base = declarative_base()

# --- ГЛОБАЛЬНЫЙ ЛОК ДЛЯ ЗАПИСИ В БД ---
DB_WRITE_LOCK = asyncio.Lock()


class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    name = Column(String)
    end_time = Column(String)  # "YYYY-MM-DD HH:MM:SS"
    active = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)
    tminus3_sent = Column(Boolean, default=False)
    onday_sent = Column(Boolean, default=False)
    after_sent = Column(Boolean, default=False)


class Pending(Base):
    __tablename__ = 'pending'
    user_id = Column(Integer, primary_key=True)
    created_at = Column(String)  # "YYYY-MM-DD HH:MM:SS"


class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, default=1)
    notif_master = Column(Boolean, default=True)
    notif_tminus3 = Column(Boolean, default=True)
    notif_onday = Column(Boolean, default=True)
    notif_after = Column(Boolean, default=True)


engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}?timeout=30", echo=False, pool_pre_ping=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _safe_commit(session: AsyncSession, retries: int = 10) -> None:
    delay = 0.1
    for attempt in range(1, retries + 1):
        try:
            await session.commit()
            return
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                await session.rollback()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)
                continue
            raise
    raise RuntimeError("Commit failed after multiple retries due to database locks")


async def _migrate_users_table():
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql("PRAGMA table_info('users')")
        cols = {row[1] for row in res.fetchall()}
        if "name" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN name TEXT")
        if "approved" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0")
        if "tminus3_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN tminus3_sent BOOLEAN DEFAULT 0")
        if "onday_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN onday_sent BOOLEAN DEFAULT 0")
        if "after_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN after_sent BOOLEAN DEFAULT 0")


async def _ensure_settings_row():
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            if not await session.get(Settings, 1):
                session.add(Settings(id=1))
                await _safe_commit(session)


async def init_db():
    # Этап установки PRAGMA
    for attempt in range(30):
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("PRAGMA busy_timeout=30000;")
                res = await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                logger.info(f"SQLite journal_mode set to: {res.scalar()}")
                await conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
            break
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                delay = min(0.5 * (attempt + 1), 5.0)
                logger.warning(f"PRAGMA phase locked (attempt {attempt + 1}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise RuntimeError("Failed to set PRAGMA settings after multiple retries.")

    # Этап создания таблиц
    for attempt in range(30):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                delay = min(0.5 * (attempt + 1), 5.0)
                logger.warning(f"create_all locked (attempt {attempt + 1}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise RuntimeError("Failed to create tables after multiple retries.")

    await _migrate_users_table()
    await _ensure_settings_row()


# ---------- users ----------
async def approve_user(user_id: int, name: str):
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            row = await session.get(User, user_id)
            if row:
                row.approved = True
                row.name = name
            else:
                session.add(User(user_id=user_id, name=name, approved=True))
            await _safe_commit(session)


async def set_end_time(user_id: int, end_time_str: str):
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    end_time=end_time_str,
                    active=True,
                    tminus3_sent=False,
                    onday_sent=False,
                    after_sent=False
                )
            )
            await session.execute(stmt)
            await _safe_commit(session)


async def get_user_end_time(user_id: int) -> Optional[str]:
    async with async_session() as session:
        return await session.scalar(select(User.end_time).where(User.user_id == user_id))


async def is_user_approved(user_id: int) -> bool:
    async with async_session() as session:
        return await session.scalar(select(User.approved).where(User.user_id == user_id)) or False


async def get_all_users() -> list[tuple[int, Optional[str], Optional[str], bool, bool]]:
    async with async_session() as session:
        result = await session.execute(
            select(User.user_id, User.name, User.end_time, User.approved, User.active)
        )
        return result.all()


async def get_active_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(select(User.user_id, User.end_time).where(User.active == True))
        return result.all()


# ---------- pending ----------
async def add_pending(user_id: int) -> bool:
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            if await session.scalar(select(User.approved).where(User.user_id == user_id)):
                return False
            if await session.get(Pending, user_id):
                return False

            session.add(Pending(user_id=user_id, created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            await _safe_commit(session)
            return True


async def remove_pending(user_id: int):
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            row = await session.get(Pending, user_id)
            if row:
                await session.delete(row)
                await _safe_commit(session)


async def get_pending_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(select(Pending.user_id, Pending.created_at))
        return result.all()


# ---------- settings ----------
async def get_settings() -> dict:
    async with async_session() as session:
        row = await session.get(Settings, 1)
        if not row:
            # Возвращаем дефолтные настройки, если в БД еще нет строки
            return {'master': True, 'tminus3': True, 'onday': True, 'after': True}
        return {
            'master': bool(row.notif_master),
            'tminus3': bool(row.notif_tminus3),
            'onday': bool(row.notif_onday),
            'after': bool(row.notif_after),
        }


async def toggle_setting(key: str) -> dict:
    key_map = {"master": "notif_master", "tminus3": "notif_tminus3", "onday": "notif_onday", "after": "notif_after"}
    if key not in key_map:
        return await get_settings()

    attr = key_map[key]
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            row = await session.get(Settings, 1)
            if not row:
                row = Settings(id=1)
                session.add(row)
            # Переключаем значение атрибута
            setattr(row, attr, not getattr(row, attr, False))
            await _safe_commit(session)
    return await get_settings()


# ========== ВОТ ВОССТАНОВЛЕННАЯ ФУНКЦИЯ ==========
async def set_all_notifications(value: bool) -> dict:
    """Включает или выключает все уведомления разом."""
    async with DB_WRITE_LOCK:
        async with async_session() as session:
            row = await session.get(Settings, 1)
            if not row:
                row = Settings(id=1)
                session.add(row)
            row.notif_master = value
            row.notif_tminus3 = value
            row.notif_onday = value
            row.notif_after = value
            await _safe_commit(session)
    return await get_settings()


# =================================================


# --- IDEMPOTENT SCHEDULER HELPERS ---
async def claim_tminus3_users(now_utc: datetime, tz: 'ZoneInfo') -> List[tuple[int, str]]:
    target_date_str = (now_utc.astimezone(tz).date() - timedelta(days=3)).strftime('%Y-%m-%d')

    async with DB_WRITE_LOCK:
        async with async_session() as session:
            select_stmt = select(User.user_id, User.end_time).where(
                and_(
                    User.active == True,
                    User.tminus3_sent == False,
                    User.end_time.is_not(None),
                    User.end_time.startswith(target_date_str)
                )
            )
            users_to_notify = (await session.execute(select_stmt)).all()
            if not users_to_notify:
                return []

            user_ids = [uid for uid, _ in users_to_notify]
            update_stmt = update(User).where(User.user_id.in_(user_ids)).values(tminus3_sent=True)
            await session.execute(update_stmt)
            await _safe_commit(session)
            return users_to_notify


async def claim_onday_users(now_utc: datetime, tz: 'ZoneInfo') -> List[tuple[int, str]]:
    target_date_str = now_utc.astimezone(tz).date().strftime('%Y-%m-%d')

    async with DB_WRITE_LOCK:
        async with async_session() as session:
            select_stmt = select(User.user_id, User.end_time).where(
                and_(
                    User.active == True,
                    User.onday_sent == False,
                    User.end_time.is_not(None),
                    User.end_time.startswith(target_date_str),
                    User.end_time >= f"{target_date_str} 11:00:00"
                )
            )
            users_to_notify = (await session.execute(select_stmt)).all()
            if not users_to_notify:
                return []

            user_ids = [uid for uid, _ in users_to_notify]
            update_stmt = update(User).where(User.user_id.in_(user_ids)).values(onday_sent=True)
            await session.execute(update_stmt)
            await _safe_commit(session)
            return users_to_notify


async def claim_after_expiry_users(now_utc: datetime) -> List[tuple[int, str]]:
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    window_start_str = (now_utc - timedelta(minutes=65)).strftime("%Y-%m-%d %H:%M:%S")

    async with DB_WRITE_LOCK:
        async with async_session() as session:
            select_stmt = select(User.user_id, User.end_time).where(
                and_(
                    User.active == True,
                    User.after_sent == False,
                    User.end_time.is_not(None),
                    User.end_time <= now_str,
                    User.end_time > window_start_str
                )
            )
            users_to_notify = (await session.execute(select_stmt)).all()
            if not users_to_notify:
                return []

            user_ids = [uid for uid, _ in users_to_notify]
            update_stmt = update(User).where(User.user_id.in_(user_ids)).values(after_sent=True, active=False)
            await session.execute(update_stmt)
            await _safe_commit(session)
            return users_to_notify


async def dispose_db():
    await engine.dispose()