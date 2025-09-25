import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

from app.scheduler import start_scheduler
from app.handlers.user import router as user_router
from app.handlers.admin import router as admin_router
from app.db import init_db, dispose_db
from config import Config

logger = logging.getLogger(__name__)

def build_bot() -> Bot:
    session = AiohttpSession(timeout=75)  # секунды
    return Bot(
        token=Config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

async def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    await init_db()

    dp = Dispatcher()
    dp.include_router(user_router)
    dp.include_router(admin_router)

    scheduler_task = None

    async def on_startup(bot: Bot):
        nonlocal scheduler_task
        scheduler_task = start_scheduler(bot)

    async def on_shutdown():
        if scheduler_task:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        with suppress(Exception):
            await dispose_db()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    backoff = 2
    while True:
        bot = build_bot()
        try:
            await dp.start_polling(bot)
            break
        except TelegramNetworkError as e:
            logger.warning(f"Polling network error: {e!r}. Retry in {backoff}s")
            with suppress(Exception):
                await bot.session.close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            logger.exception(f"Polling crashed: {e!r}. Retry in 5s")
            with suppress(Exception):
                await bot.session.close()
            await asyncio.sleep(5)
