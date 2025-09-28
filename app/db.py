from __future__ import annotations
from typing import Optional
from pathlib import Path
import logging
from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker
import asyncio
import os

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "/data/bot.db"))
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id  = Column(Integer, primary_key=True)
    name     = Column(String)                      # <-- НОВОЕ: имя пользователя
    end_time = Column(String)                      # "YYYY-MM-DD HH:MM:SS"
    active   = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)

    tminus3_sent = Column(Boolean, default=False)
    onday_sent   = Column(Boolean, default=False)
    after_sent   = Column(Boolean, default=False)

class Pending(Base):
    __tablename__ = 'pending'
    user_id    = Column(Integer, primary_key=True)
    created_at = Column(String)                    # "YYYY-MM-DD HH:MM:SS"

# Глобальные настройки уведомлений
class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, default=1)
    notif_master  = Column(Boolean, default=True)
    notif_tminus3 = Column(Boolean, default=True)
    notif_onday   = Column(Boolean, default=True)
    notif_after   = Column(Boolean, default=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}?timeout=30", echo=False, pool_pre_ping=True, connect_args={"timeout": 30},)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def _safe_commit(session, retries: int = 5, base_delay: float = 0.2):
    """
    Коммит с экспоненциальной задержкой при sqlite 'database is locked'.
    Даём шанс конкурентной транзакции закончить запись.
    """
    delay = base_delay
    for attempt in range(1, retries + 1):
        try:
            await _safe_commit(session)
            return
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.warning(f"Commit locked (attempt {attempt}/{retries}), retry in {delay:.2f}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)  # максимум 2 секунды между повторами
                continue
            raise
    # Последний шанс: пусть бросит исключение, если не получилось
    await _safe_commit(session)


async def _migrate_users_table():
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql("PRAGMA table_info('users')")
        cols = {row[1] for row in res.fetchall()}
        if "name" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN name TEXT")  # <- добавили имя
        if "approved" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0")
        if "tminus3_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN tminus3_sent BOOLEAN DEFAULT 0")
        if "onday_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN onday_sent BOOLEAN DEFAULT 0")
        if "after_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN after_sent BOOLEAN DEFAULT 0")

async def _ensure_settings_row():
    async with async_session() as session:
        row = await session.get(Settings, 1)
        if not row:
            session.add(Settings(id=1, notif_master=True, notif_tminus3=True, notif_onday=True, notif_after=True))
            await _safe_commit(session)

async def init_db():
    """
    1) Сначала пытаемся выставить безопасные PRAGMA:
       - busy_timeout (чтобы эта коннекция ждала при локах)
       - проверяем journal_mode; если не WAL — пробуем включить
       - включаем synchronous=NORMAL и foreign_keys=ON
       Все действия с ретраями (до ~60 сек суммарно).
    2) Создаём таблицы (идемпотентно) — тоже с ретраями.
    3) Локальные миграции и дефолтные настройки.
    """
    # --- Шаг 1: PRAGMA с ретраями ---
    attempt = 0
    while True:
        attempt += 1
        try:
            async with engine.begin() as conn:
                # Важно: сначала увеличим busy_timeout для самой этой коннекции
                await conn.exec_driver_sql("PRAGMA busy_timeout=30000;")

                # Проверим текущий journal_mode, чтобы не дергать WAL зря
                cur_mode = (await conn.exec_driver_sql("PRAGMA journal_mode;")).scalar()
                cur_mode = (str(cur_mode) if cur_mode is not None else "").lower()

                if cur_mode != "wal":
                    # Попробуем включить WAL (может требовать эксклюзивный лок)
                    try:
                        new_mode = (await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")).scalar()
                        logger.info(f"SQLite journal_mode set to: {new_mode}")
                    except OperationalError as e:
                        if "database is locked" in str(e).lower():
                            # Это не критично — просто оставим текущий режим и пойдём дальше
                            logger.warning("Unable to switch to WAL now (locked). Continue with current journal_mode.")
                        else:
                            raise

                # Остальные безопасные PRAGMA
                await conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

            break  # PRAGMA этап прошёл
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                # Подождём и повторим (экспоненциальная задержка до 5 сек)
                delay = min(0.5 * attempt, 5.0)
                logger.warning(f"PRAGMA phase locked (attempt {attempt}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                # Дадим шанс до 30 попыток (~минуту)
                if attempt < 30:
                    continue
            raise

    # --- Шаг 2: create_all с ретраями ---
    attempt = 0
    while True:
        attempt += 1
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < 30:
                delay = min(0.5 * attempt, 5.0)
                logger.warning(f"create_all locked (attempt {attempt}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                continue
            raise

    # --- Шаг 3: миграции и дефолтные значения ---
    await _migrate_users_table()
    await _ensure_settings_row()

# ---------- helpers ----------
def _truthy(val) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val != 0
    if isinstance(val, (bytes, str)):
        s = (val.decode() if isinstance(val, bytes) else val).strip().lower()
        return s in {"1", "true", "t", "yes", "y"}
    return bool(val)

# ---------- users ----------
async def add_user(user_id: int):
    async with async_session() as session:
        row = await session.get(User, user_id)
        if not row:
            session.add(User(
                user_id=user_id, name=None, end_time=None,
                active=False, approved=False,
                tminus3_sent=False, onday_sent=False, after_sent=False
            ))
            await _safe_commit(session)

async def approve_user(user_id: int, name: str):
    """Одобрить пользователя и сохранить имя (создать при необходимости)."""
    name = (name or "").strip()
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            row.approved = True
            if name:
                row.name = name
        else:
            session.add(User(
                user_id=user_id, name=(name or None), end_time=None,
                active=False, approved=True,
                tminus3_sent=False, onday_sent=False, after_sent=False
            ))
        await _safe_commit(session)

async def set_end_time(user_id: int, end_time: str):
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            row.end_time = end_time
            row.active = True
            row.tminus3_sent = False
            row.onday_sent = False
            row.after_sent = False
        else:
            session.add(User(
                user_id=user_id, name=None, end_time=end_time,
                active=True, approved=True,
                tminus3_sent=False, onday_sent=False, after_sent=False
            ))
        await _safe_commit(session)

async def get_user_end_time(user_id: int) -> Optional[str]:
    async with async_session() as session:
        result = await session.execute(select(User.end_time).where(User.user_id == user_id))
        return result.scalar()

async def is_user_approved(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(User.approved).where(User.user_id == user_id))
        return _truthy(result.scalar())

async def get_active_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(select(User.user_id, User.end_time).where(User.active == True))
        return [(r[0], r[1]) for r in result.fetchall()]

async def get_active_users_with_flags() -> list[tuple[int, Optional[str], bool, bool, bool]]:
    async with async_session() as session:
        result = await session.execute(
            select(User.user_id, User.end_time, User.tminus3_sent, User.onday_sent, User.after_sent)
            .where(User.active == True)
        )
        return [tuple(r) for r in result.fetchall()]  # type: ignore

async def update_active_status(user_id: int, active: bool):
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            row.active = active
            await _safe_commit(session)

async def mark_flag(user_id: int, field: str, value: bool = True):
    if field not in {"tminus3_sent", "onday_sent", "after_sent"}:
        return
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            setattr(row, field, value)
            await _safe_commit(session)

# ---------- pending ----------
async def add_pending(user_id: int) -> bool:
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row and _truthy(row.approved):
            return False
        if await session.get(Pending, user_id):
            return False
        from datetime import datetime
        session.add(Pending(user_id=user_id, created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await _safe_commit(session)
        return True

async def remove_pending(user_id: int):
    async with async_session() as session:
        row = await session.get(Pending, user_id)
        if row:
            await session.delete(row)
            await _safe_commit(session)

async def get_pending_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(select(Pending.user_id, Pending.created_at))
        return [(r[0], r[1]) for r in result.fetchall()]

# ---------- dashboard / lists ----------
async def get_all_users() -> list[tuple[int, Optional[str], Optional[str], bool, bool]]:
    """(user_id, name, end_time, approved, active)"""
    async with async_session() as session:
        result = await session.execute(
            select(User.user_id, User.name, User.end_time, User.approved, User.active)
        )
        return [tuple(r) for r in result.fetchall()]  # type: ignore

# ---------- settings ----------
async def get_settings() -> dict:
    async with async_session() as session:
        row = await session.get(Settings, 1)
        if not row:
            row = Settings(id=1)
            session.add(row)
            await _safe_commit(session)
        return dict(
            master=bool(row.notif_master),
            tminus3=bool(row.notif_tminus3),
            onday=bool(row.notif_onday),
            after=bool(row.notif_after),
        )

async def toggle_setting(key: str) -> dict:
    key_map = {"master": "notif_master", "tminus3": "notif_tminus3", "onday": "notif_onday", "after": "notif_after"}
    if key not in key_map:
        return await get_settings()
    attr = key_map[key]
    async with async_session() as session:
        row = await session.get(Settings, 1)
        if not row:
            row = Settings(id=1)
            session.add(row)
        current = bool(getattr(row, attr, False))
        setattr(row, attr, not current)
        await _safe_commit(session)
    return await get_settings()

async def set_all_notifications(value: bool) -> dict:
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

async def dispose_db():
    await engine.dispose()
