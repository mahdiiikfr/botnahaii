import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import THROTTLING_RATE_LIMIT

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware to prevent spamming of messages and callback queries.
    Uses a lightweight, in-memory dictionary cache (user_id -> last_timestamp).
    For CallbackQueries, alerts users via a pop-up without altering the UI.
    For Messages, ignores or silently rejects inputs that violate the rate limit.
    """
    def __init__(self, rate_limit: float = THROTTLING_RATE_LIMIT):
        super().__init__()
        self.rate_limit = rate_limit
        # In-memory dictionary to track requests: user_id -> last_request_time
        self.cache: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None

        # Extract user_id from the Telegram event
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None:
            now = time.time()
            last_time = self.cache.get(user_id, 0.0)

            if now - last_time < self.rate_limit:
                # User is spamming
                logger.warning(f"Throttled user {user_id}. Attempted request too quickly.")
                if isinstance(event, CallbackQuery):
                    # Answer the callback query with a visual Telegram alert
                    await event.answer(
                        text="Please slow down! 🐢",
                        show_alert=True
                    )
                # Silently block further middleware/handler execution
                return

            # Update cache timestamp for the user
            self.cache[user_id] = now

        return await handler(event, data)
