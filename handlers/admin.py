import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import format_breadcrumbs

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

@router.callback_query(F.data.startswith("admin_approve:"))
async def handle_admin_approval(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Approve Payment' callback query button click.
    - Database: Updates status to 'paid' -> 'delivered'.
    - Admin UI: Removes inline buttons, updates text dynamically to status approved ("وضعیت: ✅ تایید شده").
    - Customer UI: Retrieves 'digital_data' (auto-delivery key) and sends dynamic beautiful report to client.
    """
    order_id = int(callback_query.data.split(":")[1])

    # Fetch order and product details
    async with db._conn.execute(
        """
        SELECT o.id, o.user_id, o.status, p.name, p.digital_data
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.id = ?;
        """, (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد یا حذف شده است!", show_alert=True)
        return

    if order["status"] in ("paid", "delivered"):
        await callback_query.answer("⚠️ این سفارش قبلاً تایید و تحویل داده شده است!", show_alert=True)
        # Update admin layout anyway to sync UI
        await _clean_admin_ui(callback_query, order_id, is_approved=True)
        return

    # 1. Update order status in DB to delivered
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin Interface (remove buttons, mark as approved)
    await _clean_admin_ui(callback_query, order_id, is_approved=True)
    await callback_query.answer("✅ سفارش با موفقیت تایید و تحویل داده شد.")

    # 3. Notify and Deliver digital product to customer beautifully in Farsi
    breadcrumbs = format_breadcrumbs("home")
    delivery_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 پرداخت شما تایید شد! سفارش تحویل داده شد.</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول خریداری شده:</b> {order['name']}\n\n"
        f"🗝️ <b>لایسنس / اطلاعات دیجیتال محصول:</b>\n"
        f"<code>{order['digital_data'] or 'تحویل دستی (به زودی ارسال می‌شود)'}</code>\n\n"
        "از خرید شما صمیمانه سپاسگزاریم! جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        # We can send a new message, or try to edit a previous message if we saved it.
        # Since this is async/push delivery, sending a direct message is standard and highly reliable.
        await bot.send_message(
            chat_id=order["user_id"],
            text=delivery_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Delivered order digital keys #{order_id} directly to customer {order['user_id']}.")
    except Exception as e:
        logger.error(f"Failed to deliver key message to customer {order['user_id']}: {e}")

@router.callback_query(F.data.startswith("admin_reject:"))
async def handle_admin_rejection(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Reject Payment' callback query button click.
    - Database: Updates status to 'rejected'.
    - Admin UI: Removes inline buttons, updates text dynamically to status rejected ("وضعیت: ❌ رد شده").
    - Customer UI: Sends rejection notification prompting customer to contact support.
    """
    order_id = int(callback_query.data.split(":")[1])

    # Fetch order and product details
    async with db._conn.execute(
        "SELECT id, user_id, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد!", show_alert=True)
        return

    if order["status"] == "rejected":
        await callback_query.answer("⚠️ این سفارش قبلاً رد شده است!", show_alert=True)
        await _clean_admin_ui(callback_query, order_id, is_approved=False)
        return

    # 1. Update DB order status to rejected
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin Interface
    await _clean_admin_ui(callback_query, order_id, is_approved=False)
    await callback_query.answer("❌ سفارش رد شد.")

    # 3. Notify Customer of rejection in Farsi
    breadcrumbs = format_breadcrumbs("home")
    rejection_text = (
        f"{breadcrumbs}\n\n"
        f"<b>⚠️ پرداخت شما رد شد!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n\n"
        "متأسفانه واریز رسید ثبت شده شما توسط مدیریت تایید نگردید.\n"
        "خواهشمند است اطلاعات پرداخت خود را مجدداً بررسی کرده یا جهت پیگیری بیشتر با پشتیبانی در ارتباط باشید.\n\n"
        "جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید:"
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.send_message(
            chat_id=order["user_id"],
            text=rejection_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Dispatched rejection notification for order #{order_id} to user {order['user_id']}.")
    except Exception as e:
        logger.error(f"Failed to notify customer {order['user_id']} of rejection: {e}")

async def _clean_admin_ui(callback_query: CallbackQuery, order_id: int, is_approved: bool):
    """
    Cleans up the admin's action matrix to prevent double clicks.
    Edits original layout caption or text, appending the static status, and removes inline keyboards.
    """
    original_text = callback_query.message.text or callback_query.message.caption or ""

    status_suffix = "\n\n<b>وضعیت: ✅ تأیید شده و تحویل گردید</b>" if is_approved else "\n\n<b>وضعیت: ❌ تراکنش رد شد</b>"
    updated_text = original_text + status_suffix

    try:
        if callback_query.message.caption:
            await callback_query.message.edit_caption(
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            await callback_query.message.edit_text(
                text=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to clean admin interface for order #{order_id}: {e}")
