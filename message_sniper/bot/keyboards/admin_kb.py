"""Admin Keyboards"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def back_kb(target: str = "admin_menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=target)
    return kb.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="👥 Пользователи", callback_data="admin_users")
    kb.button(text="💌 Начислить баланс", callback_data="admin_credit")
    kb.button(text="🚫 Бан/Разбан", callback_data="admin_ban_user")
    kb.button(text="📢 Рассылка всем", callback_data="admin_broadcast")
    kb.button(text="◀️ Главное меню", callback_data="main_menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()
