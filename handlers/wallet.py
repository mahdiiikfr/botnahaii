import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import DatabaseManager
from keyboards.inline import MenuCallback, CategoryCallback
from utils.ui import edit_message_safely, format_breadcrumbs, format_currency
from handlers.payment import get_checkout_keyboard

logger = logging.getLogger(__name__)

router = Router(name="wallet_router")

# --- FSM States ---
class DepositStates(StatesGroup):
    waiting_for_amount = State()

# --- Keyboard Builders ---
def get_profile_keyboard() -> InlineKeyboardMarkup:
    """
    Inline keyboard displayed in Profile/Wallet home.
    - Recharging balance ("💳 شارژ کیف پول")
    - Referrals view ("🤝 زیرمجموعه‌گیری")
    - Return to home ("🏠 بازگشت به خانه")
    """
    builder = InlineKeyboardBuilder()

    charge_button = InlineKeyboardButton(
        text="💳 شارژ کیف پول",
        callback_data="wallet_deposit"
    )

    referral_button = InlineKeyboardButton(
        text="🤝 زیرمجموعه‌گیری",
        callback_data=MenuCallback(action="referrals").pack()
    )

    back_button = InlineKeyboardButton(
        text="🏠 بازگشت به خانه",
        callback_data=MenuCallback(action="home").pack(),
        style="danger"
    )

    builder.row(charge_button)
    builder.row(referral_button)
    builder.row(back_button)

    return builder.as_markup()

# --- Handlers ---

@router.callback_query(MenuCallback.filter(F.action == "wallet"))
async def handle_profile_wallet(callback_query: CallbackQuery, db: DatabaseManager, state: FSMContext):
    """
    Renders user's Profile & Wallet info screen (Farsi, SPA style).
    Displays balance, join date, total orders count, and referral statistics.
    """
    await state.clear()
    user_id = callback_query.from_user.id
    user_data = await db.get_user(user_id)

    if not user_data:
        await callback_query.answer("⚠️ خطا: اطلاعات کاربری یافت نشد!", show_alert=True)
        return

    # Gather stats
    total_orders = await db.get_total_user_orders_count(user_id)
    invited_count = await db.get_invited_users_count(user_id)
    formatted_balance = format_currency(user_data["wallet_balance"])

    # Simple Farsi format for join date
    join_date_raw = user_data["join_date"]

    breadcrumbs = format_breadcrumbs("home")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>👤 حساب کاربری و کیف پول شما</b>\n\n"
        f"🆔 <b>شناسه کاربری:</b> <code>{user_id}</code>\n"
        f"🗓️ <b>تاریخ عضویت:</b> {join_date_raw}\n\n"
        f"💰 <b>موجودی کیف پول:</b> {formatted_balance}\n"
        f"📦 <b>تعداد خریدهای موفق:</b> {total_orders} سفارش\n"
        f"🤝 <b>تعداد زیرمجموعه‌ها:</b> {invited_count} نفر\n\n"
        "جهت افزایش اعتبار حساب خود یا مدیریت زیرمجموعه‌ها از گزینه‌های زیر استفاده کنید 👇"
    )

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=get_profile_keyboard()
    )
    await callback_query.answer()

@router.callback_query(F.data == "wallet_deposit")
async def handle_wallet_deposit_prompt(callback_query: CallbackQuery, state: FSMContext):
    """
    Prompts user to enter their custom charging amount in Toman (using FSM).
    All user messages are deleted immediately after typing.
    """
    await state.set_state(DepositStates.waiting_for_amount)

    # Save current SPA message ID to edit it once user inputs amount
    await state.update_data(deposit_message_id=callback_query.message.message_id)

    breadcrumbs = format_breadcrumbs("home")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>💳 شارژ کیف پول (افزایش اعتبار)</b>\n\n"
        "لطفاً مبلغ مورد نظر خود را جهت شارژ کیف پول به <b>تومان</b> تایپ و ارسال کنید:\n"
        "مثال: <code>50000</code>\n\n"
        "⚠️ ربات به صورت خودکار پیام تایپ‌شده شما را حذف خواهد کرد تا نظم چت حفظ گردد."
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

@router.message(DepositStates.waiting_for_amount, F.text)
async def handle_deposit_amount_entered(message: Message, state: FSMContext, bot: Bot):
    """
    Captures custom recharge amount.
    Validates the text to ensure integer formatting.
    Immediately deletes user's typing message.
    Redirects to payment gateway selectors (product_id = None represents deposit).
    """
    user_id = message.from_user.id
    raw_text = message.text.strip()

    # 1. Immediately delete user's input message to maintain clean SPA chat
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete deposit input message: {e}")

    # 2. Extract SPA message ID
    state_data = await state.get_data()
    spa_message_id = state_data["deposit_message_id"]

    # 3. Validate positive integer
    try:
        amount = int(raw_text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        # Prompt error screen directly inside SPA view
        breadcrumbs = format_breadcrumbs("home")
        error_text = (
            f"{breadcrumbs}\n\n"
            "<b>⚠️ خطای مقدار ورودی!</b>\n\n"
            "مبلغ وارد شده معتبر نیست. لطفاً مبلغ شارژ را به صورت عدد مثبت بزرگتر از صفر تایپ و ارسال کنید.\n"
            "مثال: <code>50000</code>"
        )
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data=MenuCallback(action="wallet").pack(), style="danger")]
        ])
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=spa_message_id,
                text=error_text,
                reply_markup=cancel_keyboard,
                parse_mode="HTML"
            )
        except Exception as edit_err:
            logger.error(f"Failed to show deposit error: {edit_err}")
        return

    # Clear FSM State
    await state.clear()

    # Formulate pre-invoice for deposit
    breadcrumbs = format_breadcrumbs("home")
    formatted_price = format_currency(amount)

    text = (
        f"{breadcrumbs}\n\n"
        f"<b>💳 پیش‌فاکتور افزایش اعتبار کیف پول:</b>\n\n"
        f"💰 <b>مبلغ شارژ درخواستی:</b> {formatted_price}\n\n"
        "لطفاً روش پرداخت خود را جهت نهایی‌سازی فاکتور انتخاب کنید:"
    )

    # We reuse the checkout payment structure from Phase 4
    # To represent a wallet deposit, we use product_id = 0, but since product_id is nullable in schema,
    # we represent it cleanly by using custom callback mapping (pay_online:0:0:1 or pay_card:0:0:1).
    # We store the selected deposit amount in FSM or pass it directly in checkout routing.
    # To keep it extremely robust and type-safe, we generate a custom checkout keyboard:
    builder = InlineKeyboardBuilder()

    online_button = InlineKeyboardButton(
        text="💳 درگاه پرداخت آنلاین",
        callback_data=f"dep_online:{amount}",
        style="primary"
    )

    card_button = InlineKeyboardButton(
        text="کارت به کارت 💳",
        callback_data=f"dep_card:{amount}",
        style="primary"
    )

    back_button = InlineKeyboardButton(
        text="❌ انصراف و لغو فاکتور",
        callback_data=MenuCallback(action="wallet").pack(),
        style="danger"
    )

    builder.row(online_button)
    builder.row(card_button)
    builder.row(back_button)

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=spa_message_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to render deposit checkout selectors: {e}")
