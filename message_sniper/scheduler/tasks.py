"""
Scheduler & Mailing Engine - Message Sniper Bot
Uses APScheduler + Telethon for actual message sending
"""

import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, UserBannedInChannelError,
    ChatWriteForbiddenError, ChannelPrivateError,
    SlowModeWaitError, PeerFloodError
)
from sqlalchemy import select

from database.db import AsyncSessionFactory, Campaign, CampaignLog, TelegramAccount, User
from database.db import CampaignStatus, AccountStatus
from config import settings

logger = logging.getLogger(__name__)

TELETHON_API_ID = 12345        # <-- my.telegram.org
TELETHON_API_HASH = "your_hash"  # <-- my.telegram.org

_scheduler: Optional[AsyncIOScheduler] = None
_bot: Optional[Bot] = None


async def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    global _scheduler, _bot
    _bot = bot

    jobstores = {
        "default": RedisJobStore(host="localhost", port=6379, db=1)
    }

    _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    _scheduler.add_job(
        process_queued_campaigns,
        "interval",
        seconds=30,
        id="campaign_processor",
        replace_existing=True
    )

    return _scheduler


async def enqueue_campaign(campaign_id: int, user_telegram_id: int):
    """Called when user confirms a campaign — sets status to QUEUED"""
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if campaign:
            campaign.status = CampaignStatus.QUEUED
            await session.commit()
    logger.info(f"Campaign {campaign_id} enqueued")


async def process_queued_campaigns():
    """Picks up QUEUED campaigns and runs them"""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.QUEUED).limit(3)
        )
        campaigns = result.scalars().all()

    for campaign in campaigns:
        asyncio.create_task(run_campaign(campaign.id))


async def run_campaign(campaign_id: int):
    """Main mailing loop for a single campaign"""
    logger.info(f"Starting campaign {campaign_id}")

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()

        if not campaign or campaign.status not in [CampaignStatus.QUEUED, CampaignStatus.RUNNING]:
            return

        # Mark as running
        campaign.status = CampaignStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        await session.commit()

        # Load user
        user_result = await session.execute(select(User).where(User.id == campaign.user_id))
        user = user_result.scalar_one_or_none()

        # Load active accounts
        accounts_result = await session.execute(
            select(TelegramAccount).where(
                TelegramAccount.user_id == campaign.user_id,
                TelegramAccount.status == AccountStatus.ACTIVE
            )
        )
        accounts = accounts_result.scalars().all()

    if not accounts:
        await _fail_campaign(campaign_id, "Нет активных аккаунтов-отправителей")
        return

    target_groups = json.loads(campaign.target_groups)
    sent_count = campaign.messages_sent
    account_index = 0
    remaining = campaign.messages_to_send - sent_count

    for group in target_groups:
        if sent_count >= campaign.messages_to_send:
            break

        # Check if campaign was paused
        async with AsyncSessionFactory() as session:
            check = await session.execute(select(Campaign.status).where(Campaign.id == campaign_id))
            status = check.scalar_one_or_none()
            if status == CampaignStatus.PAUSED:
                logger.info(f"Campaign {campaign_id} paused")
                return

        # Rotate accounts
        account = accounts[account_index % len(accounts)]
        account_index += 1

        success, error = await send_message_to_group(
            account=account,
            group=group,
            text=campaign.message_text,
            media_file_id=campaign.media_file_id
        )

        # Log result
        async with AsyncSessionFactory() as session:
            log = CampaignLog(
                campaign_id=campaign_id,
                group_target=str(group),
                account_phone=account.phone,
                success=success,
                error_message=error
            )
            session.add(log)

            # Update campaign progress
            camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
            camp = camp_result.scalar_one_or_none()

            if success:
                camp.messages_sent += 1
                sent_count += 1
            else:
                camp.messages_failed += 1

            await session.commit()

        if success:
            logger.info(f"[Campaign {campaign_id}] ✅ Sent to {group}")
        else:
            logger.warning(f"[Campaign {campaign_id}] ❌ Failed {group}: {error}")

        # Delay between sends (anti-spam)
        await asyncio.sleep(settings.DELAY_BETWEEN_MESSAGES)

    # Mark complete
    async with AsyncSessionFactory() as session:
        camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        camp = camp_result.scalar_one_or_none()
        if camp and camp.status == CampaignStatus.RUNNING:
            camp.status = CampaignStatus.COMPLETED
            camp.completed_at = datetime.utcnow()
            await session.commit()

    # Notify user
    if _bot:
        try:
            async with AsyncSessionFactory() as session:
                camp_result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
                camp = camp_result.scalar_one_or_none()
                user_result = await session.execute(select(User).where(User.id == camp.user_id))
                user = user_result.scalar_one_or_none()

            rate = round((camp.messages_sent / max(camp.messages_to_send, 1)) * 100, 1)
            await _bot.send_message(
                user.telegram_id,
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"📌 {camp.name}\n"
                f"📨 Отправлено: {camp.messages_sent}/{camp.messages_to_send}\n"
                f"❌ Ошибок: {camp.messages_failed}\n"
                f"📈 Доставляемость: {rate}%"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    logger.info(f"Campaign {campaign_id} completed. Sent: {sent_count}")


async def send_message_to_group(
    account: TelegramAccount,
    group: str,
    text: str,
    media_file_id: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """Send one message to one group using Telethon"""

    client = TelegramClient(
        StringSession(account.session_string),
        TELETHON_API_ID,
        TELETHON_API_HASH
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            await _mark_account_expired(account.id)
            return False, "Session expired"

        if media_file_id:
            # For media we need the file bytes — simplified: send text only
            # In production: download from Telegram then re-upload via Telethon
            await client.send_message(group, text, parse_mode="html")
        else:
            await client.send_message(group, text, parse_mode="html")

        # Update account stats
        async with AsyncSessionFactory() as session:
            acc_result = await session.execute(
                select(TelegramAccount).where(TelegramAccount.id == account.id)
            )
            acc = acc_result.scalar_one_or_none()
            if acc:
                acc.messages_sent += 1
            await session.commit()

        await client.disconnect()
        return True, None

    except FloodWaitError as e:
        wait_seconds = e.seconds
        await _mark_account_flood(account.id, wait_seconds)
        await client.disconnect()
        await asyncio.sleep(min(wait_seconds, 60))
        return False, f"FloodWait {wait_seconds}s"

    except PeerFloodError:
        await _mark_account_flood(account.id, 3600)
        await client.disconnect()
        return False, "PeerFlood — account temporarily blocked"

    except (ChatWriteForbiddenError, ChannelPrivateError, UserBannedInChannelError) as e:
        await client.disconnect()
        return False, f"Access denied: {type(e).__name__}"

    except SlowModeWaitError as e:
        await client.disconnect()
        return False, f"SlowMode: wait {e.seconds}s"

    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        return False, str(e)[:200]


async def _fail_campaign(campaign_id: int, reason: str):
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        camp = result.scalar_one_or_none()
        if camp:
            camp.status = CampaignStatus.FAILED
            await session.commit()
    logger.error(f"Campaign {campaign_id} failed: {reason}")


async def _mark_account_expired(account_id: int):
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(TelegramAccount).where(TelegramAccount.id == account_id))
        acc = result.scalar_one_or_none()
        if acc:
            acc.status = AccountStatus.SESSION_EXPIRED
            await session.commit()


async def _mark_account_flood(account_id: int, wait_seconds: int):
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(TelegramAccount).where(TelegramAccount.id == account_id))
        acc = result.scalar_one_or_none()
        if acc:
            acc.status = AccountStatus.FLOOD_WAIT
            acc.flood_wait_until = datetime.utcnow() + timedelta(seconds=wait_seconds)
            await session.commit()
