"""
Admin Panel Handler - Message Sniper Bot
"""

from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, desc

from database.db import AsyncSessionFactory, User, Payment, Campaign, PaymentStatus
from bot.keyboards.admin_kb import admin_menu_kb, back_kb
from config import settings

router = Router()


def admin_only(handler):
    async def wrapper(event, *args, **kwargs):
        user_id = event.from_user.id
        if user_id not in settings.ADMIN_IDS:
            return
        return await handler(event, *args, **kwargs)
    return wrapper


class BroadcastFSM(StatesGroup):
    enter_message = State()


class ManualCreditFSM(StatesGroup):
    enter_user_id = State()
    enter_amount = State()


# ─── Admin Menu ────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_menu(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    async with AsyncSessionFactory() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        total_revenue = await session.scalar(
            select(func.sum(Payment.amount_usd)).where(Payment.status == PaymentStatus.COMPLETED)
        ) or 0
        active_campaigns = await session.scalar(
            select(func.count(Campaign.id)).where(Campaign.status.in_(["running", "queued"]))
        )

        # New users today
        today = datetime.utcnow().date()
        new_today = await session.scalar(
            select(func.count(User.id)).where(func.date(User.created_at) == today)
        )

    text = f"""
🛠️ <b>Admin Panel — Message Sniper</b>

📊 <b>Статистика:</b>
👥 Всего пользователей: <b>{total_users}</b>
🆕 Новых сегодня: <b>{new_today}</b>
💰 Общая выручка: <b>${total_revenue:.2f}</b>
🚀 Активных рассылок: <b>{active_campaigns}</b>

Выберите действие:
"""
    await message.answer(text, reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(call: CallbackQuery):
    if call.from_user.id not in settings.ADMIN_IDS:
        return
    await admin_menu(call.message)


# ─── Users Management ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    if call.from_user.id not in settings.ADMIN_IDS:
        return

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User).order_by(desc(User.created_at)).limit(20)
        )
        users = result.scalars().all()

    text = "👥 <b>Последние 20 пользователей:</b>\n\n"
    for u in users:
        ban_icon = "🚫" if u.is_banned else "✅"
        text += f"{ban_icon} <code>{u.telegram_id}</code> @{u.username or 'N/A'} — 💌{u.messages_balance}\n"

    await call.message.edit_text(text, reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_ban_user")
async def admin_ban_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in settings.ADMIN_IDS:
        return

    await state.set_state(ManualCreditFSM.enter_user_id)
    await state.update_data(action="ban")
    await call.message.edit_text(
        "🚫 <b>Забанить пользователя</b>\n\nВведите Telegram ID:",
        reply_markup=back_kb("admin_menu")
    )


# ─── Manual Credit ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_credit")
async def admin_credit_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in settings.ADMIN_IDS:
        return

    await state.set_state(ManualCreditFSM.enter_user_id)
    await state.update_data(action="credit")
    await call.message.edit_text(
        "💌 <b>Ручное начисление баланса</b>\n\nВведите Telegram ID пользователя:",
        reply_markup=back_kb("admin_menu")
    )


@router.message(ManualCreditFSM.enter_user_id)
async def admin_credit_user_id(message: Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID")
        return

    data = await state.get_data()
    await state.update_data(target_id=target_id)

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Пользователь не найден")
        await state.clear()
        return

    if data["action"] == "ban":
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(User).where(User.telegram_id == target_id))
            u = result.scalar_one_or_none()
            u.is_banned = not u.is_banned
            status = "забанен" if u.is_banned else "разбанен"
            await session.commit()
        await state.clear()
        await message.answer(f"{'🚫' if u.is_banned else '✅'} Пользователь {target_id} {status}", reply_markup=admin_menu_kb())
        return

    await state.set_state(ManualCreditFSM.enter_amount)
    await message.answer(
        f"✅ Найден: {user.full_name} (@{user.username})\n"
        f"💌 Текущий баланс: {user.messages_balance}\n\n"
        "Введите количество сообщений для начисления:"
    )


@router.message(ManualCreditFSM.enter_amount)
async def admin_credit_amount(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число")
        return

    data = await state.get_data()
    await state.clear()

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.telegram_id == data["target_id"]))
        user = result.scalar_one_or_none()
        user.messages_balance += amount
        await session.commit()

    await message.answer(
        f"✅ <b>Начислено {amount} отправок</b>\n"
        f"Пользователю: {data['target_id']}\n"
        f"Новый баланс: {user.messages_balance}",
        reply_markup=admin_menu_kb()
    )

    # Notify user
    try:
        await bot.send_message(
            data["target_id"],
            f"🎁 <b>На ваш баланс начислено {amount} отправок!</b>\n\n"
            f"💌 Текущий баланс: {user.messages_balance}"
        )
    except Exception:
        pass


# ─── Statistics ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id not in settings.ADMIN_IDS:
        return

    async with AsyncSessionFactory() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        total_revenue = await session.scalar(
            select(func.sum(Payment.amount_usd)).where(Payment.status == PaymentStatus.COMPLETED)
        ) or 0
        total_payments = await session.scalar(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.COMPLETED)
        )
        total_campaigns = await session.scalar(select(func.count(Campaign.id)))
        total_sent = await session.scalar(select(func.sum(Campaign.messages_sent))) or 0

        # Week revenue
        week_ago = datetime.utcnow() - timedelta(days=7)
        week_revenue = await session.scalar(
            select(func.sum(Payment.amount_usd)).where(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= week_ago
            )
        ) or 0

    text = f"""
📊 <b>Полная статистика</b>

<b>👥 Пользователи:</b>
• Всего: {total_users}

<b>💰 Финансы:</b>
• Общая выручка: ${total_revenue:.2f}
• За 7 дней: ${week_revenue:.2f}
• Успешных платежей: {total_payments}
• Средний чек: ${(total_revenue / max(total_payments, 1)):.2f}

<b>📨 Рассылки:</b>
• Всего кампаний: {total_campaigns}
• Сообщений отправлено: {total_sent:,}
"""
    await call.message.edit_text(text, reply_markup=admin_menu_kb())


# ─── Broadcast to all users ────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in settings.ADMIN_IDS:
        return

    await state.set_state(BroadcastFSM.enter_message)
    await call.message.edit_text(
        "📢 <b>Рассылка всем пользователям</b>\n\nВведите текст сообщения:",
        reply_markup=back_kb("admin_menu")
    )


@router.message(BroadcastFSM.enter_message)
async def admin_do_broadcast(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    await state.clear()
    text = message.text

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User.telegram_id).where(User.is_banned == False))
        user_ids = result.scalars().all()

    sent, failed = 0, 0
    status_msg = await message.answer(f"📢 Рассылаю {len(user_ids)} пользователям...")

    for uid in user_ids:
        try:
            await bot.send_message(uid, f"📢 <b>Сообщение от Message Sniper</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"✅ Доставлено: {sent}\n❌ Ошибок: {failed}",
        reply_markup=admin_menu_kb()
    )
