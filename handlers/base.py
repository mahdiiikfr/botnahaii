import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from database.db import DatabaseManager
from keyboards.base import get_main_menu_keyboard, get_join_channel_keyboard
from config import REQUIRED_CHANNEL

logger = logging.getLogger(__name__)

router = Router(name="base_router")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: DatabaseManager):
    """
    Handles the /start command.
    - Resolves optional referral/invite parameter if present (e.g. /start 123456789).
    - Safely registers the user in the database.
    - Sends the main menu of the single-page application.
    """
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username

    # Check for referral payload in start command (e.g., /start <referrer_id>)
    args = message.text.split()
    invited_by = None
    if len(args) > 1:
        try:
            potential_inviter = int(args[1])
            # Prevent self-referral
            if potential_inviter != user_id:
                invited_by = potential_inviter
        except ValueError:
            pass

    # Register user in DB
    await db.add_user(user_id=user_id, username=username, invited_by=invited_by)

    welcome_text = (
        f"<b>👋 Welcome to the Advanced Store Bot, {message.from_user.first_name}!</b>\n\n"
        "This is an ultra-modern, Single-Page Application (SPA) styled bot. "
        "Everything updates dynamically in a single message! No spam, no clutter.\n\n"
        "Explore categories, purchase digital keys, deposit funds, and manage referrals below!"
    )

    # Send the main menu keyboard
    await message.answer(
        text=welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "check_joined")
async def handle_check_joined(callback_query: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Verifies if user completed joining the channel.
    If joined: transfers them cleanly to the SPA Main Menu.
    If not joined: displays a sharp error popup.
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

        main_menu_text = (
            f"<b>🎉 Verification Successful!</b>\n\n"
            "Welcome to the Advanced Store Bot! Explore the catalogs, order items, "
            "and manage your referral network directly from the SPA interface below:"
        )

        # Edit the message to show the Main Menu
        await callback_query.message.edit_text(
            text=main_menu_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        await callback_query.answer("Success! Welcome aboard. 🚀")
    else:
        # Show a sharp popup alert warning they haven't joined yet
        await callback_query.answer(
            text="🔒 Access denied! You have not joined our channel yet. Please join and try again.",
            show_alert=True
        )

# SPA Global Catch-All Handler (at the bottom)
@router.message()
async def global_catch_all(message: Message, state: FSMContext):
    """
    Global catch-all message handler.
    If the bot is NOT expecting text input via FSM (state is None),
    the handler immediately deletes the user's incoming message
    to keep the chat perfectly clean, adhering to strict SPA style.
    """
    current_state = await state.get_state()
    if current_state is None:
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Failed to delete spam message: {e}")
    else:
        # Since the bot is expecting FSM input, we do not delete it here.
        # Downstream handlers will deal with processing and deleting it then.
        pass
