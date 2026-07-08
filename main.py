import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, DB_PATH
from database.db import DatabaseManager

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Telegram Bot...")

    # Initialize DB Manager
    db = DatabaseManager(DB_PATH)
    await db.connect()
    await db.create_tables()

    # Initialize Bot and Dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Placeholder for handlers registration in future phases
    # from handlers import some_router
    # dp.include_router(some_router)

    try:
        # Start Polling
        logger.info("Starting bot polling...")
        # Since we are not running a live bot in Phase 1, we can comment out start_polling
        # or have a fallback for local testing.
        # await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close()
        logger.info("Bot stopped and resources cleaned up.")

if __name__ == "__main__":
    # Standard entrypoint
    # For Phase 1 we won't run polling, but code is ready for execution.
    pass
