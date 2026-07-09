import logging
from aiogram import Bot
from config import ADMIN_ID
from keyboards.admin import get_admin_decision_keyboard

logger = logging.getLogger(__name__)

async def send_order_log_to_admin(
    bot: Bot,
    order_id: int,
    user_id: int,
    username: str | None,
    product_name: str,
    price_text: str,
    method_text: str,
    receipt_file_id: str | None = None
):
    """
    Formulates a comprehensive Farsi report of an order and dispatches it to ADMIN_ID.
    If a Card-to-Card receipt was uploaded, the message is dispatched as a photo caption
    with the decision buttons.
    """
    user_repr = f"@{username}" if username else "بدون نام کاربری"

    admin_text = (
        "<b>🔔 اعلان سفارش جدید (مدیریت)</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"👥 <b>خریدار:</b> {user_repr} (شناسه: <code>{user_id}</code>)\n"
        f"🛍️ <b>محصول:</b> {product_name}\n"
        f"💰 <b>مبلغ پرداختی:</b> {price_text}\n"
        f"💳 <b>روش پرداخت:</b> {method_text}\n\n"
        "لطفاً پرداخت مربوطه را بررسی کرده و تصمیم خود را ثبت کنید:"
    )

    reply_markup = get_admin_decision_keyboard(order_id)

    try:
        if receipt_file_id:
            # Send as photo with the receipt screenshot and decision buttons
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=receipt_file_id,
                caption=admin_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            # Send as standard text message (e.g. for simulated online gateways)
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        logger.info(f"Dispatched order log #{order_id} to admin {ADMIN_ID}.")
    except Exception as e:
        logger.error(f"Failed to dispatch admin notification for order #{order_id}: {e}")
