"""
Campaigns Handler - Create, manage and monitor mailing campaigns
"""

import json
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from database.db import AsyncSessionFactory, User, Campaign, CampaignLog, TelegramAccount, CampaignStatus, AccountStatus
from bot.keyboards.campaigns_kb import campaigns_menu_kb, campaign_detail_kb, back_kb
from scheduler.tasks import enqueue_campaign
from config import settings

router = Router()


class CreateCampaignFSM(StatesGroup):
    enter_name = State()
    enter_message = State()
    enter_media = State()
    enter_groups = State()
    enter_count = State()
    confirm = State()


# ─── Campaigns Menu ────────────────────────────────────────────────────────────

@router.message(Command("campaigns"))
@router.callback_query(F.data == "campaigns_menu")
async def campaigns_menu(event):
    msg = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user_result.scalar_one_or_none()

        campaigns_result = await session.execute(
            select(Campaign).where(Campaign.user_id == user.id).order_by(Campaign.created_at.desc()).limit(10)
        )
        campaigns = campaigns_result.scalars().all()

    status_icons = {
        CampaignStatus.DRAFT: "📝",
        CampaignStatus.QUEUED: "⏳",
        CampaignStatus.RUNNING: "🚀",
        CampaignStatus.PAUSED: "⏸️",
        CampaignStatus.COMPLETED: "✅",
        CampaignStatus.FAILED: "❌"
    }

    text = f"📊 <b>Мои рассылки</b>\n\n💌 Баланс: <b>{user.messages_balance}</b> отправок\n\n"

    if campaigns:
        for c in campaigns:
            icon = status_icons.get(c.status, "❓")
            progress = f"{c.messages_sent}/{c.messages_to_send}"
            text += f"{icon} <b>{c.name}</b> — {progress}\n"
    else:
        text += "<i>У вас ещё нет рассылок. Создайте первую!</i>"

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=campaigns_menu_kb(campaigns))
    else:
        await msg.answer(text, reply_markup=campaigns_menu_kb(campaigns))


# ─── Create Campaign ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "create_campaign")
async def create_campaign_start(call: CallbackQuery, state: FSMContext):
    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

    if user.messages_balance <= 0:
        await call.answer("❌ Нет баланса! Сначала купите пакет.", show_alert=True)
        return

    await state.set_state(CreateCampaignFSM.enter_name)
    await call.message.edit_text(
        "📝 <b>Создание рассылки</b>\n\n"
        "<b>Шаг 1/5:</b> Введите название кампании (для вашего удобства):",
        reply_markup=back_kb("campaigns_menu")
    )


@router.message(CreateCampaignFSM.enter_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("❌ Название должно быть от 2 до 100 символов")
        return

    await state.update_data(name=name)
    await state.set_state(CreateCampaignFSM.enter_message)
    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "<b>Шаг 2/5:</b> Напишите текст сообщения для рассылки:\n\n"
        "<i>Поддерживается HTML-разметка: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, ссылки</i>"
    )


@router.message(CreateCampaignFSM.enter_message)
async def process_message_text(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    if len(text) < 1:
        await message.answer("❌ Сообщение не может быть пустым")
        return

    await state.update_data(message_text=text)
    await state.set_state(CreateCampaignFSM.enter_media)
    await message.answer(
        "✅ Текст сохранён!\n\n"
        "<b>Шаг 3/5:</b> Прикрепите фото/видео (опционально)\n\n"
        "Отправьте медиафайл или нажмите /skip для пропуска"
    )


@router.message(CreateCampaignFSM.enter_media, F.photo)
async def process_media_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(media_file_id=file_id, media_type="photo")
    await _ask_groups(message, state)


@router.message(CreateCampaignFSM.enter_media, F.video)
async def process_media_video(message: Message, state: FSMContext):
    file_id = message.video.file_id
    await state.update_data(media_file_id=file_id, media_type="video")
    await _ask_groups(message, state)


@router.message(CreateCampaignFSM.enter_media, F.text == "/skip")
async def process_media_skip(message: Message, state: FSMContext):
    await state.update_data(media_file_id=None, media_type=None)
    await _ask_groups(message, state)


async def _ask_groups(message: Message, state: FSMContext):
    await state.set_state(CreateCampaignFSM.enter_groups)
    await message.answer(
        "✅ Медиа настроено!\n\n"
        "<b>Шаг 4/5:</b> Введите список групп/каналов для рассылки\n\n"
        "Формат — каждая группа с новой строки:\n"
        "<code>@groupname1\n@groupname2\nhttps://t.me/group3\n-1001234567890</code>\n\n"
        f"<i>Максимум {settings.MAX_GROUPS_PER_CAMPAIGN} групп</i>"
    )


@router.message(CreateCampaignFSM.enter_groups)
async def process_groups(message: Message, state: FSMContext):
    lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]

    if not lines:
        await message.answer("❌ Список групп пустой. Введите хотя бы одну группу.")
        return

    if len(lines) > settings.MAX_GROUPS_PER_CAMPAIGN:
        await message.answer(f"❌ Максимум {settings.MAX_GROUPS_PER_CAMPAIGN} групп. У вас: {len(lines)}")
        return

    await state.update_data(target_groups=lines)
    await state.set_state(CreateCampaignFSM.enter_count)

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_result.scalar_one_or_none()

    await message.answer(
        f"✅ Групп добавлено: <b>{len(lines)}</b>\n\n"
        f"<b>Шаг 5/5:</b> Сколько сообщений отправить?\n\n"
        f"💌 Ваш баланс: <b>{user.messages_balance}</b> отправок\n"
        f"📊 Доступных групп: {len(lines)}\n\n"
        f"Введите число (не больше баланса и количества групп):"
    )


@router.message(CreateCampaignFSM.enter_count)
async def process_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число")
        return

    data = await state.get_data()

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_result.scalar_one_or_none()

    if count <= 0:
        await message.answer("❌ Количество должно быть больше 0")
        return

    if count > user.messages_balance:
        await message.answer(f"❌ Недостаточно баланса. У вас: {user.messages_balance}")
        return

    if count > len(data["target_groups"]):
        count = len(data["target_groups"])

    await state.update_data(messages_to_send=count)
    await state.set_state(CreateCampaignFSM.confirm)

    media_info = "Нет" if not data.get("media_file_id") else f"Да ({data.get('media_type')})"
    confirm_text = f"""
📋 <b>Подтверждение рассылки</b>

📌 Название: <b>{data['name']}</b>
📝 Сообщение: <i>{data['message_text'][:100]}{'...' if len(data['message_text']) > 100 else ''}</i>
🖼️ Медиа: {media_info}
📍 Групп: <b>{len(data['target_groups'])}</b>
📨 Отправок: <b>{count}</b>
💌 Спишется с баланса: <b>{count}</b>

Запустить рассылку?
"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Запустить!", callback_data="confirm_campaign")
    kb.button(text="❌ Отменить", callback_data="campaigns_menu")
    kb.adjust(1)
    await message.answer(confirm_text, reply_markup=kb.as_markup())


@router.callback_query(F.data == "confirm_campaign")
async def confirm_campaign(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionFactory() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

        if user.messages_balance < data["messages_to_send"]:
            await call.answer("❌ Недостаточно баланса!", show_alert=True)
            return

        # Deduct balance
        user.messages_balance -= data["messages_to_send"]

        # Create campaign
        campaign = Campaign(
            user_id=user.id,
            name=data["name"],
            message_text=data["message_text"],
            media_file_id=data.get("media_file_id"),
            target_groups=json.dumps(data["target_groups"]),
            messages_to_send=data["messages_to_send"],
            status=CampaignStatus.QUEUED
        )
        session.add(campaign)
        await session.commit()
        await session.refresh(campaign)
        campaign_id = campaign.id

    # Enqueue in scheduler
    await enqueue_campaign(campaign_id, call.from_user.id)

    await call.message.edit_text(
        f"🚀 <b>Рассылка запущена!</b>\n\n"
        f"📌 <b>{data['name']}</b>\n"
        f"📨 Будет отправлено: {data['messages_to_send']} сообщений\n\n"
        f"Следите за прогрессом в разделе «Мои рассылки»",
        reply_markup=back_kb("campaigns_menu")
    )


# ─── Campaign Details ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("campaign_"))
async def campaign_detail(call: CallbackQuery):
    campaign_id = int(call.data.split("_")[1])

    async with AsyncSessionFactory() as session:
        camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        camp = camp_result.scalar_one_or_none()

        user_result = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
        user = user_result.scalar_one_or_none()

        if not camp or camp.user_id != user.id:
            await call.answer("❌ Кампания не найдена", show_alert=True)
            return

        success_count = await session.scalar(
            select(func.count(CampaignLog.id)).where(
                CampaignLog.campaign_id == campaign_id,
                CampaignLog.success == True
            )
        )
        fail_count = await session.scalar(
            select(func.count(CampaignLog.id)).where(
                CampaignLog.campaign_id == campaign_id,
                CampaignLog.success == False
            )
        )

    delivery_rate = round((success_count / max(camp.messages_to_send, 1)) * 100, 1)
    groups = json.loads(camp.target_groups)

    text = f"""
📊 <b>{camp.name}</b>

🔹 Статус: <b>{camp.status.value}</b>
📨 Прогресс: <b>{camp.messages_sent}/{camp.messages_to_send}</b>
✅ Доставлено: {success_count}
❌ Ошибки: {fail_count}
📈 Доставляемость: {delivery_rate}%
📍 Групп в списке: {len(groups)}
🕐 Создана: {camp.created_at.strftime('%d.%m.%Y %H:%M')}
"""

    await call.message.edit_text(text, reply_markup=campaign_detail_kb(camp))


@router.callback_query(F.data.startswith("pause_campaign_"))
async def pause_campaign(call: CallbackQuery):
    campaign_id = int(call.data.split("_")[-1])
    async with AsyncSessionFactory() as session:
        camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        camp = camp_result.scalar_one_or_none()
        if camp:
            camp.status = CampaignStatus.PAUSED
            await session.commit()
    await call.answer("⏸️ Рассылка приостановлена", show_alert=True)
    await campaign_detail(call)


@router.callback_query(F.data.startswith("resume_campaign_"))
async def resume_campaign(call: CallbackQuery):
    campaign_id = int(call.data.split("_")[-1])
    async with AsyncSessionFactory() as session:
        camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        camp = camp_result.scalar_one_or_none()
        if camp:
            camp.status = CampaignStatus.QUEUED
            await session.commit()
    await enqueue_campaign(campaign_id, call.from_user.id)
    await call.answer("▶️ Рассылка возобновлена", show_alert=True)
    await campaign_detail(call)
