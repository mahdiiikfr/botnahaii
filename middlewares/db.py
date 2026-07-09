from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from database.db import DatabaseManager

class DbMiddleware(BaseMiddleware):
    """
    Middleware to inject the DatabaseManager instance into the handler's parameters/dependencies.
    Provides clean database access to all downstream middlewares and handlers via 'db'.
    """
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Inject the DatabaseManager instance into the handler context/data dict
        data["db"] = self.db_manager
        return await handler(event, data)
