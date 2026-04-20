"""
Keyboard: Main Menu
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Мои рассылки", callback_data="campaigns_menu")
    kb.button(text="💳 Купить отправки", callback_data="buy_menu")
    kb.button(text="👤 Мой аккаунт", callback_data="account_menu")
    kb.button(text="📱 Мои аккаунты", callback_data="my_accounts")
    if is_admin:
        kb.button(text="🛠️ Админ панель", callback_data="admin_menu")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def back_kb(target: str = "main_menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=target)
    return kb.as_markup()
