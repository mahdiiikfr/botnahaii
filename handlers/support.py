import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError
from database.db import DatabaseManager
from keyboards.inline import MenuCallback
from utils.ui import edit_message_safely, format_breadcrumbs
from config import ADMIN_ID

logger = logging.getLogger(__name__)

router = Router(name="support_router")

# --- FSM States ---
class SupportStates(StatesGroup):
    waiting_for_ticket = State()
    waiting_for_admin_reply = State()

# --- Handlers ---

@router.callback_query(MenuCallback.filter(F.action == "support"))
async def handle_support_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Renders the Support / Ticketing home screen inside the single SPA message.
    """
    await state.clear()
    breadcrumbs = format_breadcrumbs("support")

    text = (
        f"{breadcrumbs}\n\n"
        "<b>ℹ️ پشتیبانی و مرکز تیکتینگ</b>\n\n"
        "به بخش پشتیبانی خوش آمدید! در این بخش می‌توانید به صورت مستقیم با مدیریت در ارتباط باشید.\n\n"
        "✉️ جهت ارسال پیام جدید به مدیریت، روی دکمه <b>«ارسال تیکت جدید»</b> کلیک کرده و سپس پیام خود را تایپ و ارسال نمایید."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ ارسال تیکت جدید", callback_data="send_ticket")],
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=keyboard
    )
    await callback_query.answer()


@router.callback_query(F.data == "send_ticket")
async def handle_send_ticket_prompt(callback_query: CallbackQuery, state: FSMContext):
    """
    Prompts the user to write and send their ticket text message.
    Sets the FSM state to waiting_for_ticket.
    """
    await state.set_state(SupportStates.waiting_for_ticket)
    # Save the SPA message ID so we can edit it once they send the ticket
    await state.update_data(
        support_spa_message_id=callback_query.message.message_id,
        support_product_id=None
    )

    breadcrumbs = format_breadcrumbs("support")
    text = (
        f"{breadcrumbs}\n\n"
        "<b>✉️ ارسال تیکت جدید</b>\n\n"
        "✍️ لطفاً پیام یا سوال خود را به صورت متنی بنویسید و ارسال کنید:\n\n"
        "⚠️ ربات به صورت خودکار پیام تایپ‌شده شما را حذف خواهد کرد تا نظم چت حفظ گردد."
    )

    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data=MenuCallback(action="support").pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=cancel_keyboard
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("prod_support:"))
async def handle_product_support_prompt(callback_query: CallbackQuery, state: FSMContext, db: DatabaseManager):
    """
    Prompts the user to send a ticket specific to a negotiable (price = 0) product.
    """
    product_id = int(callback_query.data.split(":")[1])

    # Fetch product details
    async with db._conn.execute(
        "SELECT name FROM products WHERE id = ?;", (product_id,)
    ) as cursor:
        product = await cursor.fetchone()

    if not product:
        await callback_query.answer("⚠️ محصول یافت نشد!", show_alert=True)
        return

    await state.set_state(SupportStates.waiting_for_ticket)
    await state.update_data(
        support_spa_message_id=callback_query.message.message_id,
        support_product_id=product_id,
        support_product_name=product["name"]
    )

    breadcrumbs = format_breadcrumbs("support")
    text = (
        f"{breadcrumbs}\n\n"
        f"<b>📣 سفارش محصول: {product['name']} (توافقی)</b>\n\n"
        "لطفاً توضیحات، تعداد مورد نیاز یا اطلاعات تماس خود را در یک پیام بنویسید و ارسال کنید:\n\n"
        "⚠️ ربات به صورت خودکار پیام تایپ‌شده شما را حذف خواهد کرد تا نظم چت حفظ گردد."
    )

    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و لغو", callback_data=MenuCallback(action="home").pack(), style="danger")]
    ])

    await edit_message_safely(
        event=callback_query,
        text=text,
        reply_markup=cancel_keyboard
    )
    await callback_query.answer()


@router.message(SupportStates.waiting_for_ticket, F.text)
async def handle_ticket_submitted(message: Message, state: FSMContext, bot: Bot):
    """
    Handles support ticket text submission.
    Forwards user's message to ADMIN_ID with a reply matrix.
    Deletes user's typed message immediately.
    """
    user_id = message.from_user.id
    username = message.from_user.username or "نامشخص"
    first_name = message.from_user.first_name
    ticket_text = message.text.strip()

    # Get state data
    state_data = await state.get_data()
    spa_message_id = state_data["support_spa_message_id"]
    product_id = state_data.get("support_product_id")
    product_name = state_data.get("support_product_name")

    # Clean up user message immediately
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete ticket input message: {e}")

    await state.clear()

    # Formulate ticket layout for Admin
    subject_text = f"📦 سفارش توافقی: {product_name}" if product_id else "✉️ پشتیبانی عمومی"
    admin_ticket_text = (
        f"<b>📥 تیکت جدید دریافت شد!</b>\n\n"
        f"📌 <b>موضوع:</b> {subject_text}\n"
        f"👤 <b>فرستنده:</b> {first_name} (ID: <code>{user_id}</code>)\n"
        f"🏷️ <b>نام کاربری:</b> @{username}\n\n"
        f"💬 <b>متن پیام:</b>\n"
        f"<code>{ticket_text}</code>"
    )

    admin_reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ پاسخ به تیکت", callback_data=f"admin_reply:{user_id}")]
    ])

    # Send to ADMIN_ID
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_ticket_text,
            reply_markup=admin_reply_keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to forward ticket to admin {ADMIN_ID}: {e}")

    # Notify user inside SPA message
    breadcrumbs = format_breadcrumbs("support")
    success_text = (
        f"{breadcrumbs}\n\n"
        "<b>✅ تیکت شما با موفقیت ارسال شد!</b>\n\n"
        "پیام شما برای مدیریت ارسال گردید. به محض بررسی، پاسخ پشتیبان در همین چت به صورت مستقیم برای شما ارسال خواهد شد.\n\n"
        "از شکیبایی شما متشکریم."
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=spa_message_id,
            text=success_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
    except Exception as edit_err:
        logger.error(f"Failed to show ticket success message: {edit_err}")


# --- Admin Reply Flow ---

@router.callback_query(F.data.startswith("admin_reply:"))
async def handle_admin_reply_prompt(callback_query: CallbackQuery, state: FSMContext):
    """
    Prompts the Admin to write their reply to the user.
    """
    target_user_id = int(callback_query.data.split(":")[1])

    await state.set_state(SupportStates.waiting_for_admin_reply)
    await state.update_data(
        admin_reply_target_user_id=target_user_id,
        admin_reply_message_id=callback_query.message.message_id
    )

    text = (
        f"<b>✍️ پاسخ به تیکت کاربر:</b>\n"
        f"شناسه کاربر: <code>{target_user_id}</code>\n\n"
        f"لطفاً پاسخ خود را به صورت پیام متنی بنویسید و ارسال کنید:"
    )

    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_admin_reply")]
    ])

    await callback_query.message.edit_text(
        text=text,
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )
    await callback_query.answer()


@router.callback_query(F.data == "cancel_admin_reply")
async def handle_cancel_admin_reply(callback_query: CallbackQuery, state: FSMContext):
    """
    Cancels the admin reply state.
    """
    await state.clear()
    await callback_query.message.edit_text(
        text="❌ عملیات ارسال پاسخ لغو شد.",
        reply_markup=None
    )
    await callback_query.answer()


@router.message(SupportStates.waiting_for_admin_reply, F.text)
async def handle_admin_reply_submitted(message: Message, state: FSMContext, bot: Bot):
    """
    Forwards the admin's reply text directly to the customer.
    Safely wraps in try-except block to catch user blocking.
    """
    admin_text = message.text.strip()

    # Get state context
    state_data = await state.get_data()
    target_user_id = state_data["admin_reply_target_user_id"]
    admin_spa_msg_id = state_data["admin_reply_message_id"]

    # Delete admin's typing message
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete admin reply input: {e}")

    await state.clear()

    # Send answer to customer
    customer_notified = False
    customer_notify_text = (
        "<b>🔔 پاسخ جدید از پشتیبانی دریافت شد:</b>\n\n"
        f"💬 <b>متن پاسخ مدیریت:</b>\n"
        f"<code>{admin_text}</code>"
    )

    back_home_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به صفحه اصلی", callback_data=MenuCallback(action="home").pack())]
    ])

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=customer_notify_text,
            reply_markup=back_home_keyboard,
            parse_mode="HTML"
        )
        customer_notified = True
    except TelegramForbiddenError:
        logger.warning(f"Could not notify user {target_user_id} of admin reply: User blocked the bot.")
    except TelegramAPIError as e:
        logger.error(f"Failed to notify user {target_user_id} of admin reply: {e}")

    # Update admin interface
    status_suffix = "✅ پاسخ با موفقیت برای کاربر ارسال شد." if customer_notified else "❌ ناموفق: کاربر ربات را بلاک کرده است."
    admin_success_text = (
        f"<b>📧 جزئیات پاسخ ارسال شده به {target_user_id}:</b>\n\n"
        f"<code>{admin_text}</code>\n\n"
        f"<b>وضعیت ارسال:</b> {status_suffix}"
    )

    try:
        await bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=admin_spa_msg_id,
            text=admin_success_text,
            reply_markup=None,
            parse_mode="HTML"
        )
    except Exception as err:
        logger.error(f"Failed to edit admin notification screen: {err}")
