import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from config import REQUIRED_CHANNEL

logger = logging.getLogger(__name__)

class ForceJoinMiddleware(BaseMiddleware):
    """
    Middleware to force users to join a mandatory Telegram channel.
    - Exempts the '/start' message, since they need to see the start screen to receive invite cues.
    - Exempts checking action ('check_joined') callback queries.
    - For all other requests, checks user membership. If they are not a member,
      blocks the request and edits the current message or prompts them to join.

    CRITICAL localization requirement: All user-facing text is translated to Persian (Farsi).
    """
    def __init__(self, channel_id: str = REQUIRED_CHANNEL):
        super().__init__()
        self.channel_id = channel_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        db = data.get("db")
        if db:
            self.channel_id = await db.get_setting("required_channel", REQUIRED_CHANNEL)

        if not self.channel_id or self.channel_id.lower() in ("none", "no", "disable", "disabled", "", "off"):
            return await handler(event, data)

        # Resolve the user and bot from the event context
        user_id = None
        bot = data.get("bot")

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            # Allow '/start' command to pass through, even if not subscribed
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            # Allow check_joined callback verification to process
            if event.data == "check_joined":
                return await handler(event, data)

        if not user_id or not bot:
            return await handler(event, data)

        # Verify chat membership of the user in the channel
        is_member = await self._check_membership(bot, user_id)
        if is_member:
            return await handler(event, data)

        # User is NOT a member. Intercept the request and display the Join Channel view
        logger.info(f"User {user_id} blocked. Not a member of {self.channel_id}.")

        # Build the join keyboard in Persian
        channel_url = f"https://t.me/{self.channel_id.replace('@', '')}" if self.channel_id.startswith("@") else "https://t.me/telegram"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 عضویت در کانال", url=channel_url)],
            [InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_joined")]
        ])

        text = (
            "<b>🔒 دسترسی محدود است!</b>\n\n"
            f"برای استفاده از ربات، ابتدا باید عضو کانال رسمی ما شوید:\n"
            f"👉 <b>{self.channel_id}</b>\n\n"
            "لطفاً پس از عضویت، روی دکمه <b>«✅ عضو شدم»</b> در زیر کلیک کنید."
        )

        if isinstance(event, CallbackQuery):
            # Edit the current message to display the Join Channel prompt
            try:
                await event.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
            except TelegramBadRequest:
                # Fallback if message wasn't edited
                pass
            await event.answer()
        elif isinstance(event, Message):
            # Send a new message prompting them to join
            await event.answer(text=text, reply_markup=keyboard, parse_mode="HTML")

        return  # Suppress execution of any further handlers/middlewares

    async def _check_membership(self, bot, user_id: int) -> bool:
        """
        Queries bot.get_chat_member to determine if user is a valid subscriber.
        """
        try:
            member = await bot.get_chat_member(chat_id=self.channel_id, user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                return True
        except TelegramBadRequest as e:
            # Handle situations where bot is not an administrator, or channel does not exist
            logger.error(f"Failed to check chat member {user_id} in {self.channel_id}: {e}")
            # If the channel is not found or config is placeholder, return True in local dev/testing
            if "chat not found" in str(e).lower() or "member not found" in str(e).lower():
                return True
        except Exception as e:
            logger.error(f"Error checking chat membership: {e}")
            return True
        return False
