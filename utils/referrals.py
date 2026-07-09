import logging
from aiogram import Bot
from database.db import DatabaseManager
from utils.ui import format_currency

logger = logging.getLogger(__name__)

async def apply_referral_rewards(db: DatabaseManager, bot: Bot, user_row: dict, product: dict):
    """
    Shared Referral Rewards system logic helper:
    If customer has an invited_by ID, calculates 10% of purchase price,
    adds it directly to the inviter's wallet_balance, and notifies them in Persian.
    - Catches TelegramForbiddenError or generic API limits on notification dispatches gracefully.
    """
    invited_by = user_row["invited_by"]
    if not invited_by:
        return

    commission = 10000 # Flat 10,000 Toman referral commission per purchase
    if commission <= 0:
        return

    # 1. Update inviter balance in SQLite DB
    success = await db.update_user_balance(invited_by, commission)
    if not success:
        return

    # 2. Build beautiful Persian notification
    formatted_commission = format_currency(commission)
    customer_name = f"@{user_row['username']}" if user_row['username'] else "یکی از زیرمجموعه‌های شما"

    notification_text = (
        "<b>🎉 تبریک پورسانت جدید!</b>\n\n"
        f"یکی از زیرمجموعه‌های شما ({customer_name}) خرید موفقی به مبلغ {format_currency(product['price'])} انجام داد. 😍\n\n"
        f"💰 مبلغ <b>{formatted_commission}</b> (پورسانت ثابت خرید زیرمجموعه) به صورت خودکار به کیف پول شما افزوده شد!"
    )

    try:
        await bot.send_message(
            chat_id=invited_by,
            text=notification_text,
            parse_mode="HTML"
        )
        logger.info(f"Successfully credited {commission} referral reward to inviter {invited_by}.")
    except Exception as e:
        logger.error(f"Failed to deliver referral commission direct message to {invited_by}: {e}")
