"""Payment Keyboards"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def back_kb(target: str = "buy_menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=target)
    return kb.as_markup()


def buy_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Пакеты отправок", callback_data="buy_packages")
    kb.button(text="🔄 Подписки", callback_data="buy_subscriptions")
    kb.button(text="◀️ Главное меню", callback_data="main_menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def select_plan_kb(plans: dict, plan_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, plan in plans.items():
        kb.button(
            text=f"{plan['name']} — ${plan['price_usd']}",
            callback_data=f"select_{plan_type}_{key}"
        )
    kb.button(text="◀️ Назад", callback_data="buy_menu")
    kb.adjust(1)
    return kb.as_markup()


def select_coin_kb(plan_type: str, plan_key: str, coins: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for coin in coins:
        kb.button(
            text=f"💰 {coin}",
            callback_data=f"pay_{plan_type}_{plan_key}_{coin}"
        )
    kb.button(
        text="💎 TON напрямую",
        callback_data=f"direct_ton_{plan_key}_{plan_type}"
    )
    kb.button(text="◀️ Назад", callback_data="buy_menu")
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def payment_invoice_kb(pay_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить через CryptoBot", url=pay_url)
    kb.button(text="✅ Проверить оплату", callback_data=f"check_payment_{invoice_id}")
    kb.button(text="◀️ Назад", callback_data="buy_menu")
    kb.adjust(1)
    return kb.as_markup()
