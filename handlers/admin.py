import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import format_breadcrumbs, format_currency
from utils.referrals import apply_referral_rewards

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

# --- FSM States ---
class AdminStates(StatesGroup):
    waiting_for_delivery_info = State()

# --- Handlers ---

@router.callback_query(F.data.startswith("admin_approve:"))
async def handle_admin_approval(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot, state: FSMContext):
    """
    Handles admin's 'Approve Payment' callback query button click.
    Checks order parameters:
    1. If product_id IS NULL (None): It is a Wallet Deposit.
       - Increment user's wallet balance by order's recorded amount.
       - Send a successful wallet recharge notification in Farsi.
       - Update order status to delivered.
    2. If product_id IS NOT NULL: It is a standard product purchase.
       - Do not deliver instantly. Ask Admin to type and send custom delivery credentials.
       - Transition admin to AdminStates.waiting_for_delivery_info.
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

    if order["status"] in ("delivered", "rejected"):
        await callback_query.answer("⚠️ این تراکنش قبلاً بررسی گردیده است!", show_alert=True)
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
        # Instead of delivering dummy/placeholder digital_data immediately,
        # ask the Admin to type and send custom delivery details.
        await state.set_state(AdminStates.waiting_for_delivery_info)
        await state.update_data(
            approve_order_id=order_id,
            approve_user_id=order["user_id"],
            approve_admin_msg_id=callback_query.message.message_id,
            approve_admin_caption=callback_query.message.text or callback_query.message.caption or ""
        )

        # Remove decision buttons and show input prompt
        await callback_query.message.edit_reply_markup(reply_markup=None)

        prompt_text = (
            f"<b>✍️ ارسال اطلاعات تحویل سفارش #{order_id}:</b>\n\n"
            f"لطفاً لایسنس، مشخصات کاربری اکانت، یا اطلاعات تحویل این سفارش را تایپ و ارسال کنید تا مستقیماً برای کاربر فرستاده شود:\n"
        )

        try:
            if callback_query.message.caption:
                await callback_query.message.edit_caption(
                    caption=prompt_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="cancel_admin_approve")]
                    ]),
                    parse_mode="HTML"
                )
            else:
                await callback_query.message.edit_text(
                    text=prompt_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="cancel_admin_approve")]
                    ]),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Failed to display admin delivery input prompt: {e}")
        await callback_query.answer()


@router.callback_query(F.data == "cancel_admin_approve")
async def handle_cancel_admin_approve(callback_query: CallbackQuery, state: FSMContext):
    """
    Cancels the admin custom delivery info input and restores original decision buttons.
    """
    state_data = await state.get_data()
    order_id = state_data.get("approve_order_id")
    original_caption = state_data.get("approve_admin_caption", "اعلان سفارش جدید")

    await state.clear()

    if not order_id:
        await callback_query.message.delete()
        return

    from keyboards.admin import get_admin_decision_keyboard
    try:
        if callback_query.message.caption:
            await callback_query.message.edit_caption(
                caption=original_caption,
                reply_markup=get_admin_decision_keyboard(order_id),
                parse_mode="HTML"
            )
        else:
            await callback_query.message.edit_text(
                text=original_caption,
                reply_markup=get_admin_decision_keyboard(order_id),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to restore admin decision interface: {e}")
    await callback_query.answer("عملیات لغو گردید.")


@router.message(AdminStates.waiting_for_delivery_info, F.text)
async def handle_admin_delivery_submitted(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    """
    Processes Admin's text input as custom delivery credentials.
    - Saves details inside order record in the database.
    - Sets order status as delivered.
    - Decrements stock from products table.
    - Delivers custom keys/text to customer.
    - Triggers 10% referral cashback if there's an inviter.
    - Deletes Admin's message instantly.
    """
    delivery_details = message.text.strip()

    # Get state context
    state_data = await state.get_data()
    order_id = state_data["approve_order_id"]
    user_id = state_data["approve_user_id"]
    admin_spa_msg_id = state_data["approve_admin_msg_id"]
    original_caption = state_data.get("approve_admin_caption", "")

    # Clear state and delete typing message immediately
    await state.clear()
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete admin typing message: {e}")

    # Fetch order record
    async with db._conn.execute(
        "SELECT product_id FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await bot.send_message(chat_id=message.from_user.id, text="⚠️ خطا: سفارش یافت نشد!")
        return

    # 1. Update delivery data and status to delivered in DB
    await db.update_order_delivery_data(order_id, delivery_details)
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Update Admin interface cleanly to show approved status
    status_suffix = f"\n\n<b>وضعیت: ✅ تأیید شد و تحویل گردید</b>\n<b>اطلاعات تحویلی:</b>\n<code>{delivery_details}</code>"
    updated_text = original_caption + status_suffix
    try:
        try:
            await bot.edit_message_caption(
                chat_id=message.from_user.id,
                message_id=admin_spa_msg_id,
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        except Exception:
            await bot.edit_message_text(
                chat_id=message.from_user.id,
                message_id=admin_spa_msg_id,
                text=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed to update Admin UI with delivery info: {e}")

    # 3. Fetch product details
    async with db._conn.execute(
        "SELECT name FROM products WHERE id = ?;", (order["product_id"],)
    ) as cursor:
        product = await cursor.fetchone()

    # 4. Deliver digital content cleanly to customer
    breadcrumbs = format_breadcrumbs("home")
    delivery_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 سفارش شما آماده شد و تحویل گردید!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول خریداری شده:</b> {product['name'] if product else 'خدمات وب و پشتیبانی'}\n\n"
        f"🗝️ <b>مشخصات / اطلاعات تحویل ارسال شده توسط مدیریت:</b>\n"
        f"<code>{delivery_details}</code>\n\n"
        "از خرید شما صمیمانه سپاسگزاریم! جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=delivery_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Delivered order keys #{order_id} directly to client {user_id}.")
    except TelegramForbiddenError:
        logger.warning(f"Could not deliver keys for order #{order_id}: User blocked the bot.")
    except TelegramAPIError as e:
        logger.error(f"Failed to deliver keys for order #{order_id} due to api error: {e}")

    # 5. Decrement stock
    if order["product_id"] is not None:
        async with db._conn.cursor() as cursor:
            await cursor.execute("UPDATE products SET stock = MAX(0, stock - 1) WHERE id = ?;", (order["product_id"],))
            await db._conn.commit()

    # 6. Trigger 10% Referral commission logic if applicable
    user_row = await db.get_user(user_id)
    if user_row and product:
        await apply_referral_rewards(db, bot, user_row, product)


@router.callback_query(F.data.startswith("admin_reject:"))
async def handle_admin_rejection(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Handles admin's 'Reject Payment' callback query button click.
    Updates DB order status to 'rejected'.
    Notifies customer that transaction was rejected.
    If the customer had paid using Wallet/Online simulation (status was 'paid'),
    refunds the deducted amount back to their wallet balance automatically.
    Cleans admin UI to prevent double-clicks.
    """
    order_id = int(callback_query.data.split(":")[1])

    async with db._conn.execute(
        "SELECT id, user_id, amount, status FROM orders WHERE id = ?;", (order_id,)
    ) as cursor:
        order = await cursor.fetchone()

    if not order:
        await callback_query.answer("⚠️ سفارش یافت نشد!", show_alert=True)
        return

    if order["status"] == "rejected":
        await callback_query.answer("⚠️ این سفارش قبلاً رد شده است!", show_alert=True)
        await _clean_admin_ui(callback_query, order_id, is_approved=False)
        return

    # Check if we should refund (Wallet/Gateway payments had status 'paid' originally)
    refunded = False
    refund_text = ""
    if order["status"] == "paid" and order["amount"] and order["amount"] > 0:
        await db.update_user_balance(order["user_id"], order["amount"])
        refunded = True
        refund_text = f"\n\n💰 <b>بازگشت وجه:</b> مبلغ {format_currency(order['amount'])} با موفقیت به موجودی کیف پول شما برگشت داده شد."

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
        f"<b>⚠️ سفارش شما رد شد!</b>\n\n"
        f"📦 <b>شناسه تراکنش:</b> #{order_id}\n\n"
        "متأسفانه واریز رسید ثبت شده یا سفارش شما مورد تأیید قرار نگرفت.\n"
        "خواهشمند است اطلاعات تراکنش خود را مجدداً بررسی کرده یا در صورت لزوم با بخش پشتیبانی در ارتباط باشید."
        f"{refund_text}\n\n"
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

    status_suffix = "\n\n<b>وضعیت: ✅ تأیید گردید</b>" if is_approved else "\n\n<b>وضعیت: ❌ تراکنش رد شد</b>"
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
