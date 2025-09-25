from __future__ import annotations
from typing import Optional
from pathlib import Path

from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# === ВСЕГДА один и тот же файл БД в корне проекта ===
DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    end_time = Column(String)             # "YYYY-MM-DD HH:MM:SS"
    active = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)   # ключевой флаг доступа

    tminus3_sent = Column(Boolean, default=False)
    onday_sent   = Column(Boolean, default=False)
    after_sent   = Column(Boolean, default=False)

class Pending(Base):
    __tablename__ = 'pending'
    user_id = Column(Integer, primary_key=True)
    created_at = Column(String)           # "YYYY-MM-DD HH:MM:SS"

# ВАЖНО: создаём движок по абсолютному пути
engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def _migrate_users_table():
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql("PRAGMA table_info('users')")
        cols = {row[1] for row in res.fetchall()}
        if "approved" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT 0")
        if "tminus3_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN tminus3_sent BOOLEAN DEFAULT 0")
        if "onday_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN onday_sent BOOLEAN DEFAULT 0")
        if "after_sent" not in cols:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN after_sent BOOLEAN DEFAULT 0")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_users_table()

# ---------- users ----------
async def add_user(user_id: int):
    async with async_session() as session:
        row = await session.get(User, user_id)
        if not row:
            session.add(User(
                user_id=user_id,
                end_time=None,
                active=False,
                approved=False,
                tminus3_sent=False,
                onday_sent=False,
                after_sent=False
            ))
            await session.commit()

async def approve_user(user_id: int):
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            row.approved = True
        else:
            session.add(User(
                user_id=user_id,
                end_time=None,
                active=False,
                approved=True,
                tminus3_sent=False,
                onday_sent=False,
                after_sent=False
            ))
        await session.commit()

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
                user_id=user_id,
                end_time=end_time,
                active=True,
                approved=True,
                tminus3_sent=False,
                onday_sent=False,
                after_sent=False
            ))
        await session.commit()

async def get_user_end_time(user_id: int) -> Optional[str]:
    async with async_session() as session:
        result = await session.execute(select(User.end_time).where(User.user_id == user_id))
        return result.scalar()

async def get_active_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(
            select(User.user_id, User.end_time).where(User.active == True)
        )
        rows = result.fetchall()
        return [(r[0], r[1]) for r in rows]

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
            await session.commit()

async def mark_flag(user_id: int, field: str, value: bool = True):
    if field not in {"tminus3_sent", "onday_sent", "after_sent"}:
        return
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            setattr(row, field, value)
            await session.commit()

def _truthy(val) -> bool:
    """Надёжно привести из SQLite к bool: 1/0, True/False, '1'/'0', 'true'/'false'."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int,)):
        return val != 0
    if isinstance(val, (bytes, str)):
        s = (val.decode() if isinstance(val, bytes) else val).strip().lower()
        return s in {"1", "true", "t", "yes", "y"}
    return bool(val)

async def is_user_approved(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(User.approved).where(User.user_id == user_id))
        val = result.scalar()
        return _truthy(val)

# ---------- pending ----------
async def add_pending(user_id: int) -> bool:
    async with async_session() as session:
        row = await session.get(User, user_id)
        if row:
            # если уже одобрен — заявки больше не создаём
            if _truthy(row.approved):
                return False
        if await session.get(Pending, user_id):
            return False
        from datetime import datetime
        session.add(Pending(user_id=user_id, created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await session.commit()
        return True

async def remove_pending(user_id: int):
    async with async_session() as session:
        row = await session.get(Pending, user_id)
        if row:
            await session.delete(row)
            await session.commit()

async def get_pending_users() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(select(Pending.user_id, Pending.created_at))
        rows = result.fetchall()
        return [(r[0], r[1]) for r in rows]

async def dispose_db():
    await engine.dispose()

async def get_all_users() -> list[tuple[int, Optional[str], bool, bool]]:
    """
    Возвращает список (user_id, end_time, approved, active) для всех пользователей.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User.user_id, User.end_time, User.approved, User.active)
        )
        rows = result.fetchall()
        # user_id, end_time, approved, active
        return [tuple(r) for r in rows]  # type: ignore