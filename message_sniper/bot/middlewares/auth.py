"""
Auth Middleware - Auto-register users and check bans
"""

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select

from database.db import AsyncSessionFactory, User


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        if user:
            async with AsyncSessionFactory() as session:
                result = await session.execute(select(User).where(User.telegram_id == user.id))
                db_user = result.scalar_one_or_none()

                if db_user and db_user.is_banned:
                    if isinstance(event, Message):
                        await event.answer("🚫 Ваш аккаунт заблокирован.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
                    return

                data["db_user"] = db_user

        return await handler(event, data)
