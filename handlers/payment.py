import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import DatabaseManager
from keyboards.inline import CategoryCallback, MenuCallback
from utils.ui import edit_message_safely, format_breadcrumbs, format_currency
from utils.admin_logs import send_order_log_to_admin
from config import CARD_NUMBER, CARD_HOLDER

logger = logging.getLogger(__name__)

router = Router(name="payment_router")

# --- FSM States ---
class PaymentStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_for_deposit_receipt = State()

# --- Keyboard Builders ---
def get_checkout_keyboard(product_id: int, cat_id: int, page: int) -> InlineKeyboardMarkup:
    """
    Returns checkout selection keyboard offering Pay with Wallet, Online Gateway, or Card-to-Card.
    """
    builder = InlineKeyboardBuilder()

    wallet_button = InlineKeyboardButton(
        text="💰 پرداخت از موجودی کیف پول",
        callback_data=f"pay_wallet:{product_id}:{cat_id}:{page}",
        style="success"
    )

    online_button = InlineKeyboardButton(
        text="💳 درگاه پرداخت آنلاین",
        callback_data=f"pay_online:{product_id}:{cat_id}:{page}",
        style="primary"
    )

    card_button = InlineKeyboardButton(
        text="کارت به کارت 💳",
        callback_data=f"pay_card:{product_id}:{cat_id}:{page}",
        style="primary"
    )

    back_button = InlineKeyboardButton(
        text="🔙 بازگشت به جزئیات محصول",
        callback_data=CategoryCallback(id=cat_id, page=page).pack(),
        style="danger"
    )

    builder.row(wallet_button)
    builder.row(online_button)
    builder.row(card_button)
    builder.row(back_button)

    return builder.as_markup()

def get_online_simulation_keyboard(product_id: int, cat_id: int, page: int) -> InlineKeyboardMarkup:
    """
    Returns the online payment simulation keyboard.
    """
    builder = InlineKeyboardBuilder()

    simulate_success = InlineKeyboardButton(
        text="🔗 شبیه‌ساز پرداخت موفق",
        callback_data=f"sim_success:{product_id}",
        style="success"
    )

    back_button = InlineKeyboardButton(
        text="🔙 انصراف",
        callback_data=CategoryCallback(id=cat_id, page=page).pack(),
        style="danger"
    )

    builder.row(simulate_success)
    builder.row(back_button)

    return builder.as_markup()

# --- Handlers ---

@router.callback_query(F.data.startswith("add_cart:"))
async def handle_checkout_start(callback_query: CallbackQuery, db: DatabaseManager):
    """
    Overrides or intercepts Add to Cart to trigger immediate Checkout Flow.
    Displays product checkout layout inside the same SPA message.
    """
    product_id_str = callback_query.data.split(":")[1]
    try:
        product_id = int(product_id_str)
    except ValueError:
        await callback_query.answer("⚠️ شناسه محصول نامعتبر است!", show_alert=True)
        return

    # Find the product details
    async with db._conn.execute(
        "SELECT id, category_id, name, price, description FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        await callback_query.answer("⚠️ محصول یافت نشد!", show_alert=True)
        return

    cat_id = product["category_id"]
    page = 1  # Default fallback page

    breadcrumbs = format_breadcrumbs("detail")
    formatted_price = format_currency(product["price"])

    text = (
        f"{breadcrumbs}\n\n"
        f"<b>💳 پیش‌فاکتور ثبت سفارش:</b>\n\n"
        f"🛍️ <b>نام محصول:</b> {product['name']}\n"
        f"💰 <b>مبلغ نهایی:</b> {formatted_price}\n\n"
        "لطفاً روش پرداخت مورد نظر خود را انتخاب کنید:"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_checkout_keyboard(product_id, cat_id, page)
    )
    await callback_query.answer()

# --- Wallet Purchase Flow ---
@router.callback_query(F.data.startswith("pay_wallet:"))
async def handle_wallet_checkout_pay(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Deducts balance from user's wallet_balance to instantly purchase products (bypassing admin checks).
    If balance is insufficient, shows sharp Persian alert pop-up.
    """
    parts = callback_query.data.split(":")
    prod_id, cat_id, page = int(parts[1]), int(parts[2]), int(parts[3])
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username

    # 1. Fetch user data to check balance
    user_row = await db.get_user(user_id)
    product_row = None

    async with db._conn.execute("SELECT id, name, price, digital_data FROM products WHERE id = ?;", (prod_id,)) as cursor:
        product_row = await cursor.fetchone()

    if not user_row or not product_row:
        await callback_query.answer("⚠️ اطلاعات یافت نشد!", show_alert=True)
        return

    wallet_balance = user_row["wallet_balance"]
    price = product_row["price"]

    # 2. Check balance sufficiency
    if wallet_balance < price:
        await callback_query.answer(
            text="❌ موجودی کیف پول شما کافی نیست! لطفاً ابتدا اقدام به شارژ اعتبار حساب خود کنید.",
            show_alert=True
        )
        return

    # 3. Sufficient funds! Deduct balance immediately
    await db.update_user_balance(user_id, -price)

    # 4. Create and update order to paid -> delivered instantly
    order_id = await db.create_order(user_id=user_id, product_id=prod_id, status="paid", amount=price)
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 5. Instantly Deliver product details inside the SPA message
    breadcrumbs = format_breadcrumbs("home")
    delivery_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 خرید شما با موفقیت از محل موجودی انجام شد!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول خریداری شده:</b> {product_row['name']}\n"
        f"💰 <b>مبلغ کسر شده:</b> {format_currency(price)}\n\n"
        f"🗝️ <b>لایسنس / اطلاعات دیجیتال محصول:</b>\n"
        f"<code>{product_row['digital_data'] or 'تحویل دستی (به زودی ارسال می‌شود)'}</code>\n\n"
        "از خرید شما متشکریم! جهت بازگشت به صفحه اصلی، روی دکمه زیر کلیک کنید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    await edit_message_safely(
        event=callback_query,
        text=delivery_text,
        reply_markup=back_home_keyboard
    )
    await callback_query.answer("✅ خرید موفقیت‌آمیز بود!")

    # 6. Referral Commission (10% cash-back to inviter)
    await _apply_referral_rewards(db, bot, user_row, product_row)

    # 7. Send Log Report to admin (for audit trail)
    price_text = format_currency(price)
    await send_order_log_to_admin(
        bot=bot,
        order_id=order_id,
        user_id=user_id,
        username=username,
        product_name=product_row["name"],
        price_text=price_text,
        method_text="پرداخت از محل کیف پول (ثبت فوری)"
    )

# --- Automated Online simulation ---
@router.callback_query(F.data.startswith("pay_online:"))
async def handle_online_payment(callback_query: CallbackQuery):
    """
    Displays the automated gateway simulation view.
    """
    parts = callback_query.data.split(":")
    prod_id, cat_id, page = int(parts[1]), int(parts[2]), int(parts[3])

    breadcrumbs = format_breadcrumbs("detail")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>🔗 در حال اتصال به درگاه پرداخت...</b>\n\n"
        "این صفحه شبیه‌ساز پرداخت آنلاین است. جهت نهایی کردن خرید روی دکمه شبیه‌ساز پرداخت در زیر کلیک کنید:"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_online_simulation_keyboard(prod_id, cat_id, page)
    )
    await callback_query.answer()

@router.callback_query(F.data.startswith("sim_success:"))
async def handle_simulated_success(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Processes a successful gateway payment simulation.
    Updates database order immediately to paid -> delivered.
    Automatically sends delivery message containing product digital_data.
    """
    product_id = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username

    # Fetch user data to check inviter
    user_row = await db.get_user(user_id)

    # Fetch product details
    async with db._conn.execute(
        "SELECT id, name, price, digital_data FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        await callback_query.answer("⚠️ محصول یافت نشد!", show_alert=True)
        return

    # 1. Create order in paid status
    order_id = await db.create_order(user_id=user_id, product_id=product_id, status="paid", amount=product["price"])

    # 2. Update order to delivered
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 3. Formulate and deliver digital_data beautifully in Farsi
    breadcrumbs = format_breadcrumbs("home")
    delivery_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 پرداخت شما با موفقیت تایید شد!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول خریداری شده:</b> {product['name']}\n\n"
        f"🗝️ <b>لایسنس / اطلاعات دیجیتال محصول:</b>\n"
        f"<code>{product['digital_data'] or 'تحویل دستی (به زودی ارسال می‌شود)'}</code>\n\n"
        "از خرید شما متشکریم! جهت بازگشت به صفحه اصلی، روی دکمه زیر کلیک کنید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    await edit_message_safely(
        event=callback_query,
        text=delivery_text,
        reply_markup=back_home_keyboard
    )
    await callback_query.answer("✅ پرداخت موفقیت‌آمیز بود!")

    # 4. Process Referral Reward
    if user_row:
        await _apply_referral_rewards(db, bot, user_row, product)

    # 5. Dispatch a report log to Admin
    price_text = format_currency(product["price"])
    await send_order_log_to_admin(
        bot=bot,
        order_id=order_id,
        user_id=user_id,
        username=username,
        product_name=product["name"],
        price_text=price_text,
        method_text="درگاه پرداخت آنلاین (شبیه‌سازی‌شده)"
    )

# --- Card-to-Card payment pathway ---
@router.callback_query(F.data.startswith("pay_card:"))
async def handle_card_payment(callback_query: CallbackQuery, state: FSMContext):
    """
    Displays Card-to-Card payment credentials and prompts for receipt upload via FSM.
    """
    parts = callback_query.data.split(":")
    prod_id, cat_id, page = int(parts[1]), int(parts[2]), int(parts[3])

    # Save target parameters to state to access when receipt photo is received
    await state.update_data(
        checkout_product_id=prod_id,
        checkout_cat_id=cat_id,
        checkout_page=page,
        checkout_message_id=callback_query.message.message_id
    )

    # Enter waiting for receipt state
    await state.set_state(PaymentStates.waiting_for_receipt)

    breadcrumbs = format_breadcrumbs("detail")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>💳 روش کارت به کارت (کارت به کارت)</b>\n\n"
        "لطفاً مبلغ مورد نظر را به کارت زیر واریز نمایید:\n\n"
        f"💳 <b>شماره کارت:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>بنام:</b> {CARD_HOLDER}\n\n"
        "⚠️ <b>مهم:</b> پس از واریز، لطفا تصویر رسید پرداخت خود را به صورت یک عکس فرستاده و ارسال کنید.\n"
        "ربات به صورت خودکار پیام شما را پاک می‌کند تا نظم چت حفظ شود."
    )

    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و لغو خرید", callback_data=CategoryCallback(id=cat_id, page=page).pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=cancel_keyboard
    )
    await callback_query.answer()

@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def handle_receipt_photo(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    """
    Captures receipt photo uploaded by customer.
    - Saves order to DB in pending status with payment_receipt as the file_id.
    - IMMEDIATELY deletes the user's uploaded message to keep chat perfectly clean.
    - Sends pending report to admin with decision buttons.
    """
    state_data = await state.get_data()
    product_id = state_data["checkout_product_id"]
    cat_id = state_data["checkout_cat_id"]
    page = state_data["checkout_page"]
    spa_message_id = state_data["checkout_message_id"]

    user_id = message.from_user.id
    username = message.from_user.username

    # Capture file_id
    receipt_file_id = message.photo[-1].file_id

    # Immediately delete user message
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete user receipt upload message: {e}")

    await state.clear()

    # Fetch product details
    async with db._conn.execute(
        "SELECT id, name, price FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        await bot.send_message(user_id, "⚠️ خطا: محصول مورد نظر یافت نشد.")
        return

    # Save pending order in DB
    order_id = await db.create_order(
        user_id=user_id,
        product_id=product_id,
        status="pending",
        payment_receipt=receipt_file_id,
        amount=product["price"]
    )

    breadcrumbs = format_breadcrumbs("home")
    review_text = (
        f"{breadcrumbs}\n\n"
        f"<b>⏳ رسید شما با موفقیت ثبت شد!</b>\n\n"
        f"📦 <b>شناسه سفارش:</b> #{order_id}\n"
        f"🛍️ <b>محصول درخواستی:</b> {product['name']}\n\n"
        "واریزی شما ثبت شده و در حال بررسی توسط مدیریت می‌باشد. به محض بررسی، نتیجه از طریق همین پیام به اطلاع شما خواهد رسید.\n\n"
        "جهت بازگشت به منوی اصلی روی دکمه زیر کلیک کنید:"
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=spa_message_id,
            text=review_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to update user SPA screen to Review: {e}")

    # Dispatch details log + decision buttons to ADMIN_ID
    price_text = format_currency(product["price"])
    await send_order_log_to_admin(
        bot=bot,
        order_id=order_id,
        user_id=user_id,
        username=username,
        product_name=product["name"],
        price_text=price_text,
        method_text="کارت به کارت (کارت به کارت)",
        receipt_file_id=receipt_file_id
    )

# --- Custom Wallet Deposits handlers (Phase 5) ---

@router.callback_query(F.data.startswith("dep_online:"))
async def handle_deposit_online_pay(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Online gateway simulation for wallet deposits.
    Immediately increments wallet balance and notifies user inside SPA screen.
    """
    amount = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username

    # 1. Register order as delivered (product_id = None represents a wallet deposit order)
    order_id = await db.create_order(user_id=user_id, product_id=None, status="paid", amount=amount)
    async with db._conn.cursor() as cursor:
        await cursor.execute("UPDATE orders SET status = 'delivered' WHERE id = ?;", (order_id,))
        await db._conn.commit()

    # 2. Increment wallet balance
    await db.update_user_balance(user_id, amount)

    # 3. Notify user inside SPA message
    breadcrumbs = format_breadcrumbs("home")
    success_text = (
        f"{breadcrumbs}\n\n"
        f"<b>🎉 افزایش اعتبار با موفقیت انجام شد!</b>\n\n"
        f"📦 <b>شناسه سفارش شارژ:</b> #{order_id}\n"
        f"💰 <b>مبلغ افزوده شده:</b> {format_currency(amount)}\n\n"
        "موجودی کیف پول شما بلافاصله به‌روزرسانی گردید. هم‌اکنون می‌توانید از محل موجودی اقدام به خرید محصول فرمایید."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    await edit_message_safely(
        event=callback_query,
        text=success_text,
        reply_markup=back_home_keyboard
    )
    await callback_query.answer("✅ افزایش اعتبار موفقیت‌آمیز بود!")

    # 4. Dispatch Audit log to admin
    price_text = format_currency(amount)
    await send_order_log_to_admin(
        bot=bot,
        order_id=order_id,
        user_id=user_id,
        username=username,
        product_name="افزایش اعتبار کیف پول (آنلاین)",
        price_text=price_text,
        method_text="درگاه پرداخت آنلاین (شبیه‌سازی‌شده)"
    )

@router.callback_query(F.data.startswith("dep_card:"))
async def handle_deposit_card_pay(callback_query: CallbackQuery, state: FSMContext):
    """
    Prompts user to upload Card-to-Card receipt screenshot for wallet deposits.
    Uses waiting_for_deposit_receipt state.
    """
    amount = int(callback_query.data.split(":")[1])

    # Store state attributes
    await state.update_data(
        deposit_amount=amount,
        deposit_spa_message_id=callback_query.message.message_id
    )
    await state.set_state(PaymentStates.waiting_for_deposit_receipt)

    breadcrumbs = format_breadcrumbs("home")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>💳 روش کارت به کارت (افزایش اعتبار)</b>\n\n"
        f"لطفاً مبلغ <b>{format_currency(amount)}</b> را به کارت زیر واریز نمایید:\n\n"
        f"💳 <b>شماره کارت:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>بنام:</b> {CARD_HOLDER}\n\n"
        "⚠️ <b>مهم:</b> پس از واریز، تصویر رسید پرداخت را فرستاده و ارسال نمایید.\n"
        "ربات به صورت خودکار پیام شما را پاک خواهد کرد."
    )

    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data=MenuCallback(action="wallet").pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=cancel_keyboard
    )
    await callback_query.answer()

@router.message(PaymentStates.waiting_for_deposit_receipt, F.photo)
async def handle_deposit_receipt_photo(message: Message, state: FSMContext, db: DatabaseManager, bot: Bot):
    """
    Captures receipt screenshot uploaded by user for deposit.
    - Saves order with product_id=None, status=pending and the amount.
    - Deletes user photo.
    - Sends review log to Admin.
    """
    state_data = await state.get_data()
    amount = state_data["deposit_amount"]
    spa_message_id = state_data["deposit_spa_message_id"]

    user_id = message.from_user.id
    username = message.from_user.username

    receipt_file_id = message.photo[-1].file_id

    # SPA concept: Auto-delete user's photo message immediately
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete deposit photo message: {e}")

    await state.clear()

    # Save pending deposit order in database (product_id = None)
    order_id = await db.create_order(
        user_id=user_id,
        product_id=None,
        status="pending",
        payment_receipt=receipt_file_id,
        amount=amount
    )

    breadcrumbs = format_breadcrumbs("home")
    review_text = (
        f"{breadcrumbs}\n\n"
        f"<b>⏳ رسید شما با موفقیت ثبت شد!</b>\n\n"
        f"📦 <b>شناسه سفارش افزایش اعتبار:</b> #{order_id}\n"
        f"💰 <b>مبلغ واریزی درخواستی:</b> {format_currency(amount)}\n\n"
        "واریزی رسید شما ثبت شده و در حال بررسی توسط مدیریت می‌باشد. به محض تأیید مدیریت، اعتبار حساب شما شارژ خواهد شد."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=spa_message_id,
            text=review_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to edit user message to deposit review: {e}")

    # Dispatch review details + action matrix directly to ADMIN_ID
    price_text = format_currency(amount)
    await send_order_log_to_admin(
        bot=bot,
        order_id=order_id,
        user_id=user_id,
        username=username,
        product_name="افزایش اعتبار کیف پول (کارت به کارت)",
        price_text=price_text,
        method_text="کارت به کارت (کارت به کارت)",
        receipt_file_id=receipt_file_id
    )

# --- Referral Helper Rewards logic ---
async def _apply_referral_rewards(db: DatabaseManager, bot: Bot, user_row: dict, product: dict):
    """
    Rewards system logic helper:
    If customer has an invited_by ID, calculates 10% of purchase price,
    adds it directly to the inviter's wallet_balance, and notifies them in Persian.
    """
    invited_by = user_row["invited_by"]
    if not invited_by:
        return

    # Calculate 10% cash-back commission
    commission = int(product["price"] * 0.10)
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
        f"💰 مبلغ <b>{formatted_commission}</b> (۱۰٪ پورسانت) به صورت خودکار به کیف پول شما افزوده شد!"
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
