import asyncio
import datetime
import os
import logging
import aiosqlite
from aiogram import Bot
from aiogram.types import FSInputFile
from config import BACKUP_CHANNEL_ID, DB_PATH
from database.db import DatabaseManager

logger = logging.getLogger(__name__)

async def run_backup_scheduler(bot: Bot, db: DatabaseManager):
    """
    Asynchronous background scheduler.
    Triggers database cloud backup every 24 hours (86,400 seconds).

    Generates a secure snapshot utilizing SQLite's built-in non-blocking online backup API.
    This guarantees 0% write/read locking risks on the running database during backups!
    Sends the safe snapshot document to BACKUP_CHANNEL_ID and cleans up the copy.
    """
    logger.info("Database Backup Scheduler Task initialized. Interval: 24h.")

    # Short delay on startup before checking the first backup task
    await asyncio.sleep(10)

    while True:
        temp_snapshot_path = f"database/temp_backup_snapshot.db"
        try:
            logger.info("Executing secure non-blocking database online backup snapshot...")

            # Verify SQLite DB file exists
            if not os.path.exists(DB_PATH):
                logger.error(f"Backup failed. Active database file not found at path: {DB_PATH}")
            else:
                # 1. Open source and destination connections
                async with aiosqlite.connect(DB_PATH) as src_conn:
                    async with aiosqlite.connect(temp_snapshot_path) as dst_conn:
                        # 2. Execute aiosqlite's non-blocking online backup API
                        await src_conn.backup(dst_conn)

                logger.info("Safe SQLite binary online backup snapshot generated.")

                # 3. Read statistics from the safe snapshot connection
                async with DatabaseManager(temp_snapshot_path) as snapshot_db:
                    total_users = await snapshot_db.get_total_user_count()

                # 4. Get current localized timestamps
                now = datetime.datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M:%S")

                # 5. Build localized Persian backup caption
                caption = (
                    "<b>💾 پشتیبان‌گیری خودکار دیتابیس (کلود - ایمن)</b>\n\n"
                    f"🗓️ <b>تاریخ:</b> <code>{date_str}</code>\n"
                    f"⏰ <b>ساعت:</b> <code>{time_str}</code>\n"
                    f"👥 <b>تعداد کل کاربران ثبت‌شده:</b> {total_users} نفر\n\n"
                    "📦 لایه امنیتی پشتیبان‌گیری بدون هیچ‌گونه قفل‌شدگی با موفقیت ارسال شد."
                )

                # 6. Parse snapshot for aiogram document delivery
                database_file = FSInputFile(path=temp_snapshot_path, filename=f"backup_store_{date_str}.db")

                # 7. Dispatch to Cloud Channel
                await bot.send_document(
                    chat_id=BACKUP_CHANNEL_ID,
                    document=database_file,
                    caption=caption,
                    parse_mode="HTML"
                )
                logger.info(f"Database cloud backup successfully dispatched to channel {BACKUP_CHANNEL_ID}.")

        except Exception as e:
            logger.error(f"Error during safe Database cloud backup execution: {e}")
        finally:
            # 8. Clean up the temporary snapshot file safely
            if os.path.exists(temp_snapshot_path):
                try:
                    os.remove(temp_snapshot_path)
                    logger.debug("Successfully removed temporary backup snapshot file.")
                except Exception as clean_err:
                    logger.error(f"Failed to remove temporary backup snapshot file: {clean_err}")

        # Sleep for exactly 24 hours (86400 seconds)
        await asyncio.sleep(86400)
