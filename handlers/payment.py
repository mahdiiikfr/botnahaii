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

# --- Keyboard Builders ---
def get_checkout_keyboard(product_id: int, cat_id: int, page: int) -> InlineKeyboardMarkup:
    """
    Returns checkout selection keyboard offering Online Gateway or Card-to-Card.
    """
    builder = InlineKeyboardBuilder()

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
    # We fetch products by category. Since we don't store category_id in callback, we query DB
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

    # Fetch product details
    async with db._conn.execute(
        "SELECT id, name, price, digital_data FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        await callback_query.answer("⚠️ محصول یافت نشد!", show_alert=True)
        return

    # 1. Create order in paid status
    order_id = await db.create_order(user_id=user_id, product_id=product_id, status="paid")

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

    # 4. Dispatch a report log to Admin
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
    # 1. Read stored state parameters
    state_data = await state.get_data()
    product_id = state_data["checkout_product_id"]
    cat_id = state_data["checkout_cat_id"]
    page = state_data["checkout_page"]
    spa_message_id = state_data["checkout_message_id"]

    user_id = message.from_user.id
    username = message.from_user.username

    # 2. Capture highest resolution photo file_id
    receipt_file_id = message.photo[-1].file_id

    # 3. Immediately delete user's message to avoid chat clutter (Prerequisite SPA Concept)
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete user receipt upload message: {e}")

    # 4. Clear FSM state
    await state.clear()

    # Fetch product details
    async with db._conn.execute(
        "SELECT id, name, price FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        # Fallback if product somehow went missing
        await bot.send_message(user_id, "⚠️ خطا: محصول مورد نظر یافت نشد.")
        return

    # 5. Save pending order inside database
    order_id = await db.create_order(
        user_id=user_id,
        product_id=product_id,
        status="pending",
        payment_receipt=receipt_file_id
    )

    # 6. Edit SPA message to show "Receipt Under Review" screen
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

    # 7. Dispatch comprehensive order details log + decision buttons directly to ADMIN_ID
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
