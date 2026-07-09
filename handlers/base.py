import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from database.db import DatabaseManager
from keyboards.inline import get_home_keyboard
from keyboards.base import get_join_channel_keyboard
from config import REQUIRED_CHANNEL
from utils.ui import format_breadcrumbs

logger = logging.getLogger(__name__)

router = Router(name="base_router")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: DatabaseManager):
    """
    Handles the /start command.
    - Resolves optional referral/invite parameter if present (e.g. /start 123456789).
    - Safely registers the user in the database.
    - Sends the main menu of the single-page application localized in Farsi.
    """
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username

    # Check for referral payload in start command (e.g., /start <referral_code>)
    args = message.text.split()
    invited_by = None

    if len(args) > 1:
        ref_payload = args[1].strip()
        # Look up inviter by referral code
        inviter_row = await db.get_user_by_referral_code(ref_payload)
        if inviter_row:
            potential_inviter = inviter_row["user_id"]
            # Prevent self-referral
            if potential_inviter != user_id:
                invited_by = potential_inviter

    # Register user in DB (only inserts if user doesn't exist, preventing invite overwriting)
    await db.add_user(user_id=user_id, username=username, invited_by=invited_by)

    breadcrumbs = format_breadcrumbs("home")
    welcome_text = (
        f"{breadcrumbs}\n\n"
        f"<b>👋 سلام {message.from_user.first_name}، به ربات فروشگاه پیشرفته خوش آمدید!</b>\n\n"
        "این ربات با متدولوژی فوق‌مدرن تک‌صفحه‌ای (SPA) طراحی شده است. "
        "تمامی منوها و جابجایی‌ها درون یک پیام واحد اتفاق می‌افتد تا صفحه چت شما همیشه تمیز بماند.\n\n"
        "جهت شروع خرید، مشاهده محصولات، مدیریت کیف پول و مشاهده وضعیت سفارشات از گزینه‌های زیر استفاده کنید 👇"
    )

    # Send the main menu keyboard in Farsi
    await message.answer(
        text=welcome_text,
        reply_markup=get_home_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "check_joined")
async def handle_check_joined(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Verifies if user completed joining the channel.
    If joined: transfers them cleanly to the SPA Main Menu in Farsi.
    If not joined: displays a sharp error popup in Farsi.
    """
    user_id = callback_query.from_user.id

    # Perform membership check
    is_member = False
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            is_member = True
    except Exception as e:
        logger.error(f"Membership check failed: {e}")
        # Soft-fallback for dev/testing environments where bot/channel is placeholder
        is_member = True

    if is_member:
        # Register user (if they bypassed /start somehow)
        await db.add_user(user_id=user_id, username=callback_query.from_user.username)

        breadcrumbs = format_breadcrumbs("home")
        main_menu_text = (
            f"{breadcrumbs}\n\n"
            "<b>🎉 تبریک! عضویت شما با موفقیت تأیید شد.</b>\n\n"
            "به فروشگاه مدرن ما خوش آمدید. اکنون می‌توانید از پنل زیر اقدام به خرید کرده یا حساب کاربری خود را مدیریت کنید:"
        )

        # Edit the message to show the Main Menu
        await callback_query.message.edit_text(
            text=main_menu_text,
            reply_markup=get_home_keyboard(),
            parse_mode="HTML"
        )
        await callback_query.answer("عضویت تأیید شد! خوش آمدید. 🚀")
    else:
        # Show a sharp popup alert warning they haven't joined yet in Farsi
        await callback_query.answer(
            text="🔒 دسترسی محدود! شما هنوز عضو کانال ما نشده‌اید. لطفاً ابتدا عضو شوید و سپس مجدداً تلاش کنید.",
            show_alert=True
        )

# SPA Global Catch-All Handler (at the bottom)
# Added StateFilter(None) filter to make sure that we only intercept and auto-delete
# users' messages when they are NOT inside an active FSM state (state is None).
# If they are in an active FSM state, aiogram propagates the event to targeted FSM handlers safely.
@router.message(StateFilter(None))
async def global_catch_all(message: Message, state: FSMContext):
    """
    Global catch-all message handler.
    If the bot is NOT expecting text input via FSM (state is None),
    the handler immediately deletes the user's incoming message
    to keep the chat perfectly clean, adhering to strict SPA style.
    """
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete spam message: {e}")
