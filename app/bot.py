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
    """
    Создаёт и конфигурирует экземпляр бота.
    - таймаут сессии 30 секунд
    - parse_mode по умолчанию HTML
    """
    session = AiohttpSession(timeout=30)
    return Bot(
        token=Config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

async def run():
    """Основная функция запуска бота."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.info("Initializing database...")
    await init_db()

    dp = Dispatcher()
    dp.include_router(user_router)
    dp.include_router(admin_router)

    scheduler_task = None

    @dp.startup()
    async def on_startup(bot: Bot):
        nonlocal scheduler_task
        # Убедимся, что вебхук удалён перед запуском поллинга
        await bot.delete_webhook(drop_pending_updates=True)
        scheduler_task = start_scheduler(bot)
        logger.info("Bot started polling...")

    @dp.shutdown()
    async def on_shutdown():
        logger.info("Stopping bot...")
        if scheduler_task:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        await dispose_db()
        logger.info("Bot stopped.")

    # Цикл с автоматическим перезапуском при сбоях сети
    backoff = 5  # начальная задержка перед ретраем
    while True:
        bot = build_bot()
        try:
            await dp.start_polling(bot)
            break  # Выход из цикла, если start_polling завершился штатно (например, по Ctrl+C)
        except TelegramNetworkError as e:
            logger.warning(f"Polling network error: {e}. Retrying in {backoff}s...")
        except Exception as e:
            logger.exception(f"Polling crashed with an unhandled exception: {e}. Retrying in {backoff}s...")
        finally:
            # Важно всегда закрывать сессию перед ожиданием, чтобы избежать утечек ресурсов
            await bot.session.close()
            await asyncio.sleep(backoff)