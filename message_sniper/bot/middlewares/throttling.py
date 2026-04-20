"""
Throttling Middleware - Rate limiting per user
"""

import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self.users: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id
            now = time.time()
            last_time = self.users.get(user_id, 0)

            if now - last_time < self.rate_limit:
                return  # silently drop

            self.users[user_id] = now

        return await handler(event, data)
