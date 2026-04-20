"""
Configuration Settings for Message Sniper Bot
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Bot
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///message_sniper.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CryptoBot (Telegram CryptoBot @CryptoBot)
    CRYPTO_BOT_TOKEN: str = ""
    CRYPTO_BOT_API_URL: str = "https://pay.crypt.bot/api"

    # TON Connect (direct crypto)
    TON_WALLET_ADDRESS: str = ""
    TON_API_KEY: str = ""

    # Referral
    REFERRAL_BONUS_MESSAGES: int = 50  # bonus messages for referral

    # Mailing delays (anti-spam)
    DELAY_BETWEEN_MESSAGES: float = 2.5  # seconds
    DELAY_BETWEEN_ACCOUNTS: float = 5.0  # seconds

    # Limits
    MAX_ACCOUNTS_PER_USER: int = 10
    MAX_GROUPS_PER_CAMPAIGN: int = 500

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# ─── Tariff Plans ──────────────────────────────────────────────────────────────
TARIFF_PLANS = {
    "starter": {
        "name": "🥉 Starter",
        "messages": 100,
        "price_usd": 4.99,
        "description": "Идеально для теста",
        "features": ["100 отправок", "До 5 аккаунтов", "Базовая аналитика"]
    },
    "basic": {
        "name": "🥈 Basic",
        "messages": 500,
        "price_usd": 19.99,
        "description": "Для малого бизнеса",
        "features": ["500 отправок", "До 10 аккаунтов", "Расширенная аналитика", "Приоритетная поддержка"]
    },
    "pro": {
        "name": "🥇 Pro",
        "messages": 2000,
        "price_usd": 59.99,
        "description": "Для серьёзных проектов",
        "features": ["2000 отправок", "До 10 аккаунтов", "Полная аналитика", "API доступ", "VIP поддержка"]
    },
    "unlimited": {
        "name": "💎 Unlimited",
        "messages": 10000,
        "price_usd": 149.99,
        "description": "Максимальная мощь",
        "features": ["10,000 отправок", "Безлимит аккаунтов", "White-label", "Персональный менеджер"]
    }
}

# ─── Subscription Plans ────────────────────────────────────────────────────────
SUBSCRIPTION_PLANS = {
    "daily": {
        "name": "📅 Дневной",
        "messages_per_day": 200,
        "price_usd": 9.99,
        "days": 1
    },
    "weekly": {
        "name": "📆 Недельный",
        "messages_per_day": 500,
        "price_usd": 39.99,
        "days": 7
    },
    "monthly": {
        "name": "🗓️ Месячный",
        "messages_per_day": 1000,
        "price_usd": 99.99,
        "days": 30
    }
}

# ─── Supported Cryptocurrencies ────────────────────────────────────────────────
SUPPORTED_COINS = ["USDT", "TON", "BTC", "ETH", "USDC", "BNB"]
