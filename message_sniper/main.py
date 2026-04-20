"""
Message Sniper Bot - Main Entry Point
Professional Telegram bulk messaging service
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot.handlers import start, account, campaigns, payment, admin
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from database.db import init_db
from scheduler.tasks import setup_scheduler
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🎯 Starting Message Sniper Bot...")

    # Init DB
    await init_db()

    # Init Redis storage for FSM
    storage = RedisStorage.from_url(settings.REDIS_URL)

    # Init bot & dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=storage)

    # Register middlewares
    dp.message.middleware(ThrottlingMiddleware(rate_limit=1.0))
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(account.router)
    dp.include_router(campaigns.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)

    # Setup scheduler
    scheduler = await setup_scheduler(bot)
    scheduler.start()

    # Start polling
    logger.info("✅ Bot started successfully!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)
    asyncio.run(main())
