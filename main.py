import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, DB_PATH
from database.db import DatabaseManager
from middlewares.db import DbMiddleware
from middlewares.throttling import ThrottlingMiddleware
from middlewares.force_join import ForceJoinMiddleware
from handlers.base import router as base_router
from handlers.store import router as store_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Advanced Telegram Store Bot...")

    # Initialize Database Manager (aiosqlite)
    db = DatabaseManager(DB_PATH)
    await db.connect()
    await db.create_tables()

    # Initialize Bot with default HTML parse mode using DefaultBotProperties
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    # Initialize Dispatcher
    dp = Dispatcher()

    # Register Middlewares (Register on message and callback_query routers directly)
    dp.message.outer_middleware(DbMiddleware(db))
    dp.callback_query.outer_middleware(DbMiddleware(db))

    dp.message.outer_middleware(ThrottlingMiddleware())
    dp.callback_query.outer_middleware(ThrottlingMiddleware())

    dp.message.outer_middleware(ForceJoinMiddleware())
    dp.callback_query.outer_middleware(ForceJoinMiddleware())

    # Register Routers
    dp.include_router(base_router)
    dp.include_router(store_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)

    try:
        # Graceful startup logging
        logger.info("Bot successfully loaded. Commencing polling...")
        # Start polling (Uncommented to ensure production runs correctly)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Critical error during polling execution: {e}")
    finally:
        # Graceful cleanup of resources on stop/interruption
        await bot.session.close()
        await db.close()
        logger.info("Bot and Database instances cleanly shut down.")

if __name__ == "__main__":
    # If file ran directly, run the main function asynchronously
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution terminated.")
