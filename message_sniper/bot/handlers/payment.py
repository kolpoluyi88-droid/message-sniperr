"""
Payment Handler - CryptoBot (Telegram) + Direct Crypto integration
"""

import aiohttp
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.db import AsyncSessionFactory, User, Payment, PaymentStatus
from bot.keyboards.payment_kb import (
    buy_menu_kb, select_plan_kb, select_coin_kb,
    payment_invoice_kb, back_kb
)
from config import settings, TARIFF_PLANS, SUBSCRIPTION_PLANS, SUPPORTED_COINS
from sqlalchemy import select

router = Router()


# ─── CryptoBot API ─────────────────────────────────────────────────────────────

class CryptoBotAPI:
    BASE_URL = settings.CRYPTO_BOT_API_URL

    @staticmethod
    async def create_invoice(amount: float, currency: str, description: str, payload: str) -> dict:
        headers = {"Crypto-Pay-API-Token": settings.CRYPTO_BOT_TOKEN}
        params = {
            "asset": currency,
            "amount": str(round(amount, 2)),
            "description": description,
            "payload": payload,
            "paid_btn_name": "callback",
            "paid_btn_url": f"https://t.me/{(await _get_bot_username())}",
            "expires_in": 3600  # 1 hour
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{CryptoBotAPI.BASE_URL}/createInvoice", headers=headers, json=params) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data["result"]
                raise Exception(f"CryptoBot error: {data}")

    @staticmethod
    async def get_invoices(invoice_ids: list = None) -> list:
        headers = {"Crypto-Pay-API-Token": settings.CRYPTO_BOT_TOKEN}
        params = {}
        if invoice_ids:
            params["invoice_ids"] = ",".join(map(str, invoice_ids))
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CryptoBotAPI.BASE_URL}/getInvoices", headers=headers, params=params) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data["result"]["items"]
                return []

    @staticmethod
    async def check_invoice(invoice_id: str) -> str:
        """Returns: paid / active / expired"""
        invoices = await CryptoBotAPI.get_invoices([invoice_id])
        if invoices:
            return invoices[0].get("status", "unknown")
        return "unknown"


_bot_username_cache = None
async def _get_bot_username() -> str:
    return "MessageSniperBot"  # Hardcode or fetch from bot.get_me()


# ─── Buy Menu ──────────────────────────────────────────────────────────────────

@router.message(Command("buy"))
@router.callback_query(F.data == "buy_menu")
async def buy_menu(event):
    msg = event if isinstance(event, Message) else event.message

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == event.from_user.id)
        )
        user = user_result.scalar_one_or_none()

    text = f"""
💳 <b>Пополнение баланса</b>

💌 Текущий баланс: <b>{user.messages_balance}</b> отправок

<b>Способы оплаты:</b>
• 🤖 CryptoBot (USDT, TON, BTC, ETH...)
• 💎 Прямой перевод на кошелёк TON

Выберите тип пакета:
"""
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=buy_menu_kb())
    else:
        await msg.answer(text, reply_markup=buy_menu_kb())


# ─── Package Plans ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "buy_packages")
async def buy_packages(call: CallbackQuery):
    text = "📦 <b>Пакеты отправок</b>\n\nВыберите подходящий пакет:\n\n"

    for key, plan in TARIFF_PLANS.items():
        features = " | ".join(plan["features"])
        text += f"{plan['name']} — <b>${plan['price_usd']}</b>\n<i>{features}</i>\n\n"

    await call.message.edit_text(text, reply_markup=select_plan_kb(TARIFF_PLANS, "pkg"))


@router.callback_query(F.data == "buy_subscriptions")
async def buy_subscriptions(call: CallbackQuery):
    text = "🔄 <b>Подписки</b>\n\nЕжедневное пополнение баланса:\n\n"

    for key, plan in SUBSCRIPTION_PLANS.items():
        text += (
            f"{plan['name']} — <b>${plan['price_usd']}</b>\n"
            f"<i>+{plan['messages_per_day']} отправок в день, {plan['days']} дн.</i>\n\n"
        )

    await call.message.edit_text(text, reply_markup=select_plan_kb(SUBSCRIPTION_PLANS, "sub"))


# ─── Select Coin ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("select_pkg_") | F.data.startswith("select_sub_"))
async def select_coin(call: CallbackQuery):
    parts = call.data.split("_")
    plan_type = parts[1]   # pkg or sub
    plan_key = parts[2]

    plans = TARIFF_PLANS if plan_type == "pkg" else SUBSCRIPTION_PLANS
    plan = plans.get(plan_key)

    if not plan:
        await call.answer("❌ Пакет не найден", show_alert=True)
        return

    text = (
        f"💰 <b>Оплата: {plan['name']}</b>\n\n"
        f"💵 Сумма: <b>${plan['price_usd']}</b>\n\n"
        "Выберите криптовалюту:"
    )
    await call.message.edit_text(text, reply_markup=select_coin_kb(plan_type, plan_key, SUPPORTED_COINS))


# ─── Create Invoice ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_"))
async def create_payment(call: CallbackQuery):
    # pay_{plan_type}_{plan_key}_{coin}
    parts = call.data.split("_")
    plan_type = parts[1]
    plan_key = parts[2]
    coin = parts[3]

    plans = TARIFF_PLANS if plan_type == "pkg" else SUBSCRIPTION_PLANS
    plan = plans.get(plan_key)

    if not plan:
        await call.answer("❌ Пакет не найден", show_alert=True)
        return

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

        # Create pending payment record
        payment = Payment(
            user_id=user.id,
            plan_key=plan_key,
            plan_type=plan_type,
            amount_usd=plan["price_usd"],
            currency=coin,
            status=PaymentStatus.PENDING,
            messages_credited=plan.get("messages", plan.get("messages_per_day", 0))
        )
        session.add(payment)
        await session.flush()
        payment_db_id = payment.id
        await session.commit()

    await call.message.edit_text("⏳ Создаю счёт для оплаты...")

    try:
        invoice = await CryptoBotAPI.create_invoice(
            amount=plan["price_usd"],
            currency=coin,
            description=f"Message Sniper — {plan['name']}",
            payload=f"payment_{payment_db_id}"
        )

        async with AsyncSessionFactory() as session:
            pay_result = await session.execute(select(Payment).where(Payment.id == payment_db_id))
            pay = pay_result.scalar_one_or_none()
            pay.invoice_id = str(invoice["invoice_id"])
            await session.commit()

        text = f"""
🧾 <b>Счёт создан!</b>

📦 Пакет: <b>{plan['name']}</b>
💵 Сумма: <b>${plan['price_usd']} {coin}</b>
⏰ Действует: <b>1 час</b>

Нажмите кнопку ниже для оплаты через @CryptoBot
После оплаты нажмите «Проверить оплату»
"""
        await call.message.edit_text(
            text,
            reply_markup=payment_invoice_kb(invoice["bot_invoice_url"], str(invoice["invoice_id"]))
        )

    except Exception as e:
        await call.message.edit_text(
            f"❌ Ошибка создания счёта: <code>{str(e)}</code>\n\nПопробуйте позже.",
            reply_markup=back_kb("buy_menu")
        )


# ─── Check Payment ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(call: CallbackQuery):
    invoice_id = call.data.split("_", 2)[2]

    status = await CryptoBotAPI.check_invoice(invoice_id)

    if status == "paid":
        async with AsyncSessionFactory() as session:
            pay_result = await session.execute(select(Payment).where(Payment.invoice_id == invoice_id))
            pay = pay_result.scalar_one_or_none()

            if not pay:
                await call.answer("❌ Платёж не найден", show_alert=True)
                return

            if pay.status == PaymentStatus.COMPLETED:
                await call.answer("✅ Платёж уже был обработан", show_alert=True)
                return

            # Credit messages
            user_result = await session.execute(select(User).where(User.id == pay.user_id))
            user = user_result.scalar_one_or_none()

            messages_to_add = pay.messages_credited
            user.messages_balance += messages_to_add
            user.total_spent_usd += pay.amount_usd

            pay.status = PaymentStatus.COMPLETED
            pay.paid_at = datetime.utcnow()

            await session.commit()

        await call.message.edit_text(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"✅ Зачислено: <b>+{messages_to_add}</b> отправок\n"
            f"💌 Текущий баланс: <b>{user.messages_balance}</b>",
            reply_markup=back_kb("campaigns_menu")
        )

    elif status == "active":
        await call.answer("⏳ Платёж ещё не прошёл. Подождите и попробуйте снова.", show_alert=True)

    elif status == "expired":
        async with AsyncSessionFactory() as session:
            pay_result = await session.execute(select(Payment).where(Payment.invoice_id == invoice_id))
            pay = pay_result.scalar_one_or_none()
            if pay:
                pay.status = PaymentStatus.EXPIRED
                await session.commit()
        await call.answer("❌ Счёт истёк. Создайте новый.", show_alert=True)
        await call.message.edit_text("❌ Счёт истёк.", reply_markup=back_kb("buy_menu"))

    else:
        await call.answer(f"❓ Статус: {status}", show_alert=True)


# ─── Direct TON Payment ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("direct_ton_"))
async def direct_ton_payment(call: CallbackQuery):
    parts = call.data.split("_")
    plan_key = parts[2]
    plan_type = parts[3] if len(parts) > 3 else "pkg"

    plans = TARIFF_PLANS if plan_type == "pkg" else SUBSCRIPTION_PLANS
    plan = plans.get(plan_key)

    text = f"""
💎 <b>Прямая оплата TON</b>

📦 Пакет: <b>{plan['name']}</b>
💵 Сумма: <b>${plan['price_usd']}</b>

Кошелёк для перевода:
<code>{settings.TON_WALLET_ADDRESS}</code>

<b>В комментарии к переводу укажите:</b>
<code>MS_{call.from_user.id}_{plan_key}</code>

После перевода нажмите «Я оплатил» — менеджер проверит и зачислит баланс в течение 15 минут.
"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Я оплатил", callback_data=f"ton_paid_{plan_key}_{plan_type}")
    kb.button(text="◀️ Назад", callback_data="buy_menu")
    kb.adjust(1)
    await call.message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("ton_paid_"))
async def ton_paid_notification(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    plan_key = parts[2]

    await call.answer("✅ Уведомление отправлено! Ждите зачисления.", show_alert=True)

    # Notify admins
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💎 <b>Запрос ручной проверки TON</b>\n\n"
                f"👤 Пользователь: {call.from_user.full_name} (@{call.from_user.username})\n"
                f"🆔 ID: <code>{call.from_user.id}</code>\n"
                f"📦 Пакет: {plan_key}\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            )
        except Exception:
            pass
