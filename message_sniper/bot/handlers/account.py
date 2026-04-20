"""
Account Handler - Telegram account management (Telethon sessions)
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from database.db import AsyncSessionFactory, User, TelegramAccount, AccountStatus
from bot.keyboards.account_kb import account_menu_kb, accounts_list_kb, back_kb
from config import settings

router = Router()

TELETHON_API_ID = 12345       # <-- замените на ваши данные my.telegram.org
TELETHON_API_HASH = "your_hash"  # <-- замените


class AddAccountFSM(StatesGroup):
    enter_phone = State()
    enter_code = State()
    enter_2fa = State()


# ─── Account Menu ──────────────────────────────────────────────────────────────

@router.message(Command("account"))
@router.callback_query(F.data == "account_menu")
async def account_menu(event, state: FSMContext = None):
    msg = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user_result.scalar_one_or_none()

        acc_count = await session.scalar(
            select(func.count(TelegramAccount.id)).where(TelegramAccount.user_id == user.id)
        )

    bot_link = f"https://t.me/YourBotUsername?start=ref_{user.referral_code}"

    text = f"""
👤 <b>Мой аккаунт</b>

🆔 ID: <code>{user.telegram_id}</code>
👤 Имя: {user.full_name}
📩 Баланс отправок: <b>{user.messages_balance}</b> сообщений
📱 Подключённых аккаунтов: <b>{acc_count}/{settings.MAX_ACCOUNTS_PER_USER}</b>
💰 Всего потрачено: <b>${user.total_spent_usd:.2f}</b>

🔗 <b>Реферальная ссылка:</b>
<code>{bot_link}</code>
Приглашай друзей — получай +{settings.REFERRAL_BONUS_MESSAGES} сообщений за каждого!
"""
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=account_menu_kb())
    else:
        await msg.answer(text, reply_markup=account_menu_kb())


# ─── Add Sender Account ────────────────────────────────────────────────────────

@router.callback_query(F.data == "add_account")
async def add_account_start(call: CallbackQuery, state: FSMContext):
    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()
        acc_count = await session.scalar(
            select(func.count(TelegramAccount.id)).where(TelegramAccount.user_id == user.id)
        )

    if acc_count >= settings.MAX_ACCOUNTS_PER_USER:
        await call.answer(f"❌ Максимум {settings.MAX_ACCOUNTS_PER_USER} аккаунтов", show_alert=True)
        return

    await state.set_state(AddAccountFSM.enter_phone)
    await call.message.edit_text(
        "📱 <b>Добавление аккаунта-отправителя</b>\n\n"
        "Введите номер телефона в формате:\n"
        "<code>+79991234567</code>\n\n"
        "⚠️ <i>Аккаунт должен состоять в нужных группах</i>",
        reply_markup=back_kb("account_menu")
    )


@router.message(AddAccountFSM.enter_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or len(phone) < 10:
        await message.answer("❌ Неверный формат. Используйте: <code>+79991234567</code>")
        return

    await state.update_data(phone=phone)

    # Init Telethon client and request code
    client = TelegramClient(StringSession(), TELETHON_API_ID, TELETHON_API_HASH)
    await client.connect()

    try:
        result = await client.send_code_request(phone)
        session_str = client.session.save()
        await state.update_data(session_str=session_str, phone_code_hash=result.phone_code_hash)
        await client.disconnect()

        await state.set_state(AddAccountFSM.enter_code)
        await message.answer(
            f"✅ Код отправлен на <code>{phone}</code>\n\n"
            "📨 Введите код из Telegram (без пробелов):"
        )
    except Exception as e:
        await client.disconnect()
        await state.clear()
        await message.answer(f"❌ Ошибка: <code>{str(e)}</code>\n\nПопробуйте снова /account")


@router.message(AddAccountFSM.enter_code)
async def process_code(message: Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()

    client = TelegramClient(StringSession(data["session_str"]), TELETHON_API_ID, TELETHON_API_HASH)
    await client.connect()

    try:
        await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
        session_str = client.session.save()
        await client.disconnect()

        await _save_account(message.from_user.id, data["phone"], session_str)
        await state.clear()
        await message.answer(
            f"✅ <b>Аккаунт {data['phone']} успешно добавлен!</b>\n\n"
            "Теперь вы можете использовать его для рассылок.",
            reply_markup=account_menu_kb()
        )

    except SessionPasswordNeededError:
        session_str = client.session.save()
        await state.update_data(session_str=session_str)
        await client.disconnect()
        await state.set_state(AddAccountFSM.enter_2fa)
        await message.answer("🔐 Аккаунт защищён 2FA.\nВведите пароль облачного хранилища Telegram:")

    except PhoneCodeInvalidError:
        await client.disconnect()
        await message.answer("❌ Неверный код. Попробуйте ещё раз:")

    except Exception as e:
        await client.disconnect()
        await state.clear()
        await message.answer(f"❌ Ошибка: <code>{str(e)}</code>")


@router.message(AddAccountFSM.enter_2fa)
async def process_2fa(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()

    client = TelegramClient(StringSession(data["session_str"]), TELETHON_API_ID, TELETHON_API_HASH)
    await client.connect()

    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        await client.disconnect()

        await _save_account(message.from_user.id, data["phone"], session_str)
        await state.clear()
        await message.answer(
            f"✅ <b>Аккаунт {data['phone']} добавлен с 2FA!</b>",
            reply_markup=account_menu_kb()
        )
    except Exception as e:
        await client.disconnect()
        await state.clear()
        await message.answer(f"❌ Неверный пароль: <code>{str(e)}</code>")


async def _save_account(telegram_id: int, phone: str, session_str: str):
    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_result.scalar_one_or_none()

        # Check if phone already added
        existing = await session.execute(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id,
                TelegramAccount.phone == phone
            )
        )
        acc = existing.scalar_one_or_none()

        if acc:
            acc.session_string = session_str
            acc.status = AccountStatus.ACTIVE
        else:
            new_acc = TelegramAccount(
                user_id=user.id,
                phone=phone,
                session_string=session_str,
                status=AccountStatus.ACTIVE
            )
            session.add(new_acc)

        await session.commit()


# ─── List Accounts ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_accounts")
async def my_accounts(call: CallbackQuery):
    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

        accounts_result = await session.execute(
            select(TelegramAccount).where(TelegramAccount.user_id == user.id)
        )
        accounts = accounts_result.scalars().all()

    if not accounts:
        await call.message.edit_text(
            "📱 <b>Аккаунты-отправители</b>\n\nУ вас нет добавленных аккаунтов.\nДобавьте хотя бы один для рассылки.",
            reply_markup=accounts_list_kb([])
        )
        return

    status_icons = {
        AccountStatus.ACTIVE: "🟢",
        AccountStatus.BANNED: "🔴",
        AccountStatus.FLOOD_WAIT: "🟡",
        AccountStatus.SESSION_EXPIRED: "⚫"
    }

    text = "📱 <b>Ваши аккаунты-отправители:</b>\n\n"
    for acc in accounts:
        icon = status_icons.get(acc.status, "⚪")
        text += f"{icon} <code>{acc.phone}</code> — отправлено: {acc.messages_sent}\n"

    await call.message.edit_text(text, reply_markup=accounts_list_kb(accounts))


@router.callback_query(F.data.startswith("delete_account_"))
async def delete_account(call: CallbackQuery):
    acc_id = int(call.data.split("_")[-1])

    async with AsyncSessionFactory() as session:
        acc_result = await session.execute(select(TelegramAccount).where(TelegramAccount.id == acc_id))
        acc = acc_result.scalar_one_or_none()

        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

        if acc and acc.user_id == user.id:
            await session.delete(acc)
            await session.commit()
            await call.answer("✅ Аккаунт удалён", show_alert=True)
            await my_accounts(call)
        else:
            await call.answer("❌ Аккаунт не найден", show_alert=True)
