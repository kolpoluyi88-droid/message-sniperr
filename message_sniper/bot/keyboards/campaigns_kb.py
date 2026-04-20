"""Campaigns Keyboards"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from database.db import CampaignStatus


def back_kb(target: str = "main_menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=target)
    return kb.as_markup()


def campaigns_menu_kb(campaigns) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новая рассылка", callback_data="create_campaign")

    for c in campaigns:
        icon = "🚀" if c.status == CampaignStatus.RUNNING else "📝"
        kb.button(
            text=f"{icon} {c.name[:25]}",
            callback_data=f"campaign_{c.id}"
        )

    kb.button(text="💳 Купить отправки", callback_data="buy_menu")
    kb.button(text="◀️ Меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def campaign_detail_kb(campaign) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if campaign.status == CampaignStatus.RUNNING:
        kb.button(text="⏸️ Пауза", callback_data=f"pause_campaign_{campaign.id}")
    elif campaign.status == CampaignStatus.PAUSED:
        kb.button(text="▶️ Возобновить", callback_data=f"resume_campaign_{campaign.id}")

    kb.button(text="◀️ Назад", callback_data="campaigns_menu")
    kb.adjust(1)
    return kb.as_markup()
