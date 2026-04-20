"""Account Keyboards"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def back_kb(target: str = "main_menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=target)
    return kb.as_markup()


def account_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 Мои аккаунты", callback_data="my_accounts")
    kb.button(text="➕ Добавить аккаунт", callback_data="add_account")
    kb.button(text="💳 Пополнить баланс", callback_data="buy_menu")
    kb.button(text="◀️ Главное меню", callback_data="main_menu")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def accounts_list_kb(accounts) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        kb.button(
            text=f"🗑️ Удалить {acc.phone}",
            callback_data=f"delete_account_{acc.id}"
        )
    kb.button(text="➕ Добавить аккаунт", callback_data="add_account")
    kb.button(text="◀️ Назад", callback_data="account_menu")
    kb.adjust(1)
    return kb.as_markup()
