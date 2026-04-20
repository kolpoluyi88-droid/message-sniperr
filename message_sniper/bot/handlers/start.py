"""
Start & Onboarding Handler - Message Sniper Bot
"""

import secrets
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy import select

from database.db import AsyncSessionFactory
from database.db import User
from bot.keyboards.main_menu import main_menu_kb, back_kb
from config import settings

router = Router()


def generate_referral_code() -> str:
    return secrets.token_urlsafe(6).upper()


async def get_or_create_user(telegram_id: int, username: str, full_name: str, referred_by: int = None) -> User:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            referral_code = generate_referral_code()
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                referral_code=referral_code,
                referred_by=referred_by,
                is_admin=telegram_id in settings.ADMIN_IDS
            )
            session.add(user)

            # Credit referral bonus
            if referred_by:
                ref_result = await session.execute(select(User).where(User.telegram_id == referred_by))
                referrer = ref_result.scalar_one_or_none()
                if referrer:
                    referrer.messages_balance += settings.REFERRAL_BONUS_MESSAGES

            await session.commit()
            await session.refresh(user)

        return user


WELCOME_TEXT = """
🎯 <b>Добро пожаловать в Message Sniper!</b>

Профессиональный сервис рассылки по Telegram группам и чатам.

<b>⚡️ Что умеет бот:</b>
• Массовая рассылка в тысячи групп
• Поддержка нескольких аккаунтов-отправителей
• Медиа-вложения (фото, видео, документы)
• Расписание и отложенная отправка
• Детальная статистика доставки
• Безопасные задержки между сообщениями

<b>💳 Оплата:</b> Криптовалюта через CryptoBot или напрямую

<i>Выберите действие в меню ниже 👇</i>
"""


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    referred_by = None

    # Parse referral from deep link
    if command.args and command.args.startswith("ref_"):
        ref_code = command.args[4:]
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(User).where(User.referral_code == ref_code))
            referrer = result.scalar_one_or_none()
            if referrer and referrer.telegram_id != message.from_user.id:
                referred_by = referrer.telegram_id

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        referred_by=referred_by
    )

    if user.is_banned:
        await message.answer("🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.")
        return

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(user.is_admin))


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if user:
        await message.answer("📋 <b>Главное меню</b>", reply_markup=main_menu_kb(user.is_admin))


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = """
📖 <b>Помощь — Message Sniper</b>

<b>Команды:</b>
/start — Главное меню
/menu — Открыть меню
/account — Мой аккаунт и баланс
/campaigns — Мои рассылки
/buy — Купить сообщения
/help — Эта справка

<b>Как начать:</b>
1️⃣ Купите пакет сообщений
2️⃣ Добавьте аккаунт-отправитель
3️⃣ Создайте кампанию рассылки
4️⃣ Запустите и следите за статистикой

<b>Поддержка:</b> @YourSupportUsername
"""
    await message.answer(help_text, reply_markup=back_kb())
