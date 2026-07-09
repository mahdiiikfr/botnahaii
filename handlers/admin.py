import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import format_breadcrumbs, format_currency
from utils.referrals import apply_referral_rewards

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

@router.callback_query(F.data.startswith("admin_approve:"))
async def handle_admin_approval(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Approve Payment' callback query button click.
    Checks order parameters:
    1. If product_id IS NULL (None): It is a Wallet Deposit.
       - Increment user's wallet balance by order's recorded amount.
       - Send a successful wallet recharge notification in Farsi.
    2. If product_id IS NOT NULL: It is a standard product purchase.
       - Deliver digital product license keys directly to customer.
       - Distribute 10% referral cashback commission if an inviter exists.
    Updates Admin interface dynamically to prevent double-clicks.
    """
    order_id = int(callback_query.data.split(":")[1])

    # Fetch order record
    async with db._conn.execute(
        "SELECT id, user_id, product_id, amount, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد یا حذف شده است!", show_alert=True)
        return

    if order["status"] in ("paid", "delivered"):
        await callback_query.answer("⚠️ این تراکنش قبلاً تأیید گردیده است!", show_alert=True)
        await _clean_admin_ui(callback_query, order_id, is_approved=True)
        return

    # Process based on order type (Deposit vs Product Purchase)
    if order["product_id"] is None:
        # --- A. WALLET DEPOSIT ORDER ---
        deposit_amount = order["amount"] or 0

        # 1. Update order status in DB to delivered
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
            await db._conn.commit()

        # 2. Add amount to user's wallet balance
        await db.update_user_balance(order["user_id"], deposit_amount)

        # 3. Update Admin Interface
        await _clean_admin_ui(callback_query, order_id, is_approved=True)
        await callback_query.answer("✅ افزایش اعتبار حساب کاربر با موفقیت تایید و اعمال شد.")

        # 4. Notify Customer inside their Telegram Chat (Farsi, SPA style)
        breadcrumbs = format_breadcrumbs("home")
        recharge_text = (
            f"{breadcrumbs}\n\n"
            f"<b>🎉 اعتبار حساب شما افزایش یافت!</b>\n\n"
            f"📦 <b>شناسه سفارش شارژ:</b> #{order_id}\n"
            f"💰 <b>مبلغ افزوده شده:</b> {format_currency(deposit_amount)}\n\n"
            "تراکنش واریزی شما تایید گردید و موجودی کیف پول شما با موفقیت به روزرسانی شد.\n"
            "هم‌اکنون می‌توانید از محل موجودی اقدام به تهیه خدمات نمایید."
        )

        back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
        ])

        try:
            await bot.send_message(
                chat_id=order["user_id"],
                text=recharge_text,
                reply_markup=back_home_keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Delivered successful recharge notify to user {order['user_id']}.")
        except TelegramForbiddenError:
            logger.warning(f"Could not notify customer {order['user_id']} of deposit approval: User blocked the bot.")
        except TelegramAPIError as e:
            logger.error(f"Failed to notify customer {order['user_id']} of deposit approval: {e}")

    else:
        # --- B. STANDARD PRODUCT PURCHASE ---
        # Fetch associated product digital license keys and details
        async with db._conn.execute(
            "SELECT name, digital_data, price FROM products WHERE id = ?;", (order["product_id"],)
        ) as cursor:
            product = await cursor.fetchone()

        if not product:
            await callback_query.answer("⚠️ محصول یافت نشد!", show_alert=True)
            return

        # 1. Update order status to delivered
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
            await db._conn.commit()

        # 2. Update Admin Interface
        await _clean_admin_ui(callback_query, order_id, is_approved=True)
        await callback_query.answer("✅ سفارش با موفقیت تایید و تحویل داده شد.")

        # 3. Deliver digital content cleanly to customer
        breadcrumbs = format_breadcrumbs("home")
        delivery_text = (
            f"{breadcrumbs}\n\n"
            f"<b>🎉 پرداخت شما تایید شد! سفارش تحویل داده شد.</b>\n\n"
            f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
            f"🛍️ <b>محصول خریداری شده:</b> {product['name']}\n\n"
            f"🗝️ <b>لایسنس / اطلاعات دیجیتال محصول:</b>\n"
            f"<code>{product['digital_data'] or 'تحویل دستی (به زودی ارسال می‌شود)'}</code>\n\n"
            "از خرید شما صمیمانه سپاسگزاریم! جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید."
        )

        back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
        ])

        try:
            await bot.send_message(
                chat_id=order["user_id"],
                text=delivery_text,
                reply_markup=back_home_keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Delivered order keys #{order_id} directly to client {order['user_id']}.")
        except TelegramForbiddenError:
            logger.warning(f"Could not deliver keys for order #{order_id}: User blocked the bot.")
        except TelegramAPIError as e:
            logger.error(f"Failed to deliver keys for order #{order_id} due to api error: {e}")

        # 4. Trigger 10% Referral commission logic if applicable
        user_row = await db.get_user(order["user_id"])
        if user_row:
            await apply_referral_rewards(db, bot, user_row, product)


@router.callback_query(F.data.startswith("admin_reject:"))
async def handle_admin_rejection(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Reject Payment' callback query button click.
    Updates DB order status to 'rejected'.
    Notifies customer that transaction was rejected.
    Cleans admin UI to prevent double-clicks.
    """
    order_id = int(callback_query.data.split(":")[1])

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

    # 1. Update order status to rejected in database
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin Interface
    await _clean_admin_ui(callback_query, order_id, is_approved=False)
    await callback_query.answer("❌ تراکنش با موفقیت رد شد.")

    # 3. Notify Customer of rejection (Farsi)
    breadcrumbs = format_breadcrumbs("home")
    rejection_text = (
        f"{breadcrumbs}\n\n"
        f"<b>⚠️ پرداخت شما رد شد!</b>\n\n"
        f"📦 <b>شناسه تراکنش:</b> #{order_id}\n\n"
        "متأسفانه واریز رسید ثبت شده شما مورد تأیید قرار نگرفت.\n"
        "خواهشمند است اطلاعات تراکنش خود را مجدداً بررسی کرده یا در صورت لزوم با بخش پشتیبانی در ارتباط باشید.\n\n"
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
    except TelegramForbiddenError:
        logger.warning(f"Failed to deliver rejection notify for order #{order_id}: User blocked the bot.")
    except TelegramAPIError as e:
        logger.error(f"Failed to deliver rejection notify for order #{order_id} due to api error: {e}")


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
