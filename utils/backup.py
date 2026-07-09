import asyncio
import datetime
import os
import logging
from aiogram import Bot
from aiogram.types import FSInputFile
from config import BACKUP_CHANNEL_ID, DB_PATH
from database.db import DatabaseManager

logger = logging.getLogger(__name__)

async def run_backup_scheduler(bot: Bot, db: DatabaseManager):
    """
    Asynchronous background scheduler.
    Triggers database cloud backup every 24 hours (86,400 seconds).
    Reads the database safely and dispatches DB binary file to BACKUP_CHANNEL_ID.
    """
    logger.info("Database Backup Scheduler Task initialized. Interval: 24h.")

    # Optional short delay before starting the first backup on boot
    await asyncio.sleep(10)

    while True:
        try:
            logger.info("Executing scheduled Database cloud backup...")

            # 1. Fetch total stats safely using db manager
            total_users = await db.get_total_user_count()

            # 2. Get current timestamp
            now = datetime.datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")

            # 3. Verify SQLite DB file exists
            if not os.path.exists(DB_PATH):
                logger.error(f"Backup failed. Database file not found at path: {DB_PATH}")
            else:
                # Build localized Persian backup caption
                caption = (
                    "<b>💾 پشتیبان‌گیری خودکار دیتابیس (کلود)</b>\n\n"
                    f"🗓️ <b>تاریخ:</b> <code>{date_str}</code>\n"
                    f"⏰ <b>ساعت:</b> <code>{time_str}</code>\n"
                    f"👥 <b>تعداد کل کاربران ثبت‌شده:</b> {total_users} نفر\n\n"
                    "📦 فایل دیتابیس با موفقیت پشتیبان‌گیری و ارسال شد."
                )

                # Use FSInputFile to parse local file reliably for aiogram
                database_file = FSInputFile(path=DB_PATH, filename=f"backup_store_{date_str}.db")

                # Send database to cloud channel
                await bot.send_document(
                    chat_id=BACKUP_CHANNEL_ID,
                    document=database_file,
                    caption=caption,
                    parse_mode="HTML"
                )
                logger.info(f"Database cloud backup successfully dispatched to channel {BACKUP_CHANNEL_ID}.")

        except Exception as e:
            logger.error(f"Error during Database cloud backup execution: {e}")

        # Sleep for exactly 24 hours (86400 seconds)
        await asyncio.sleep(86400)
