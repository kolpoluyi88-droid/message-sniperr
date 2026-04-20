"""
Database Models - Message Sniper Bot
SQLAlchemy async with SQLite (can switch to PostgreSQL)
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean,
    DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import enum

from config import settings


class Base(DeclarativeBase):
    pass


# ─── Enums ─────────────────────────────────────────────────────────────────────

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    BANNED = "banned"
    FLOOD_WAIT = "flood_wait"
    SESSION_EXPIRED = "session_expired"


# ─── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=True)
    full_name = Column(String(256), nullable=True)
    messages_balance = Column(Integer, default=0)  # available sends
    total_spent_usd = Column(Float, default=0.0)
    referral_code = Column(String(16), unique=True, nullable=True)
    referred_by = Column(BigInteger, nullable=True)
    is_banned = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    accounts = relationship("TelegramAccount", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")


class TelegramAccount(Base):
    """Sender Telegram accounts (via Telethon sessions)"""
    __tablename__ = "telegram_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone = Column(String(20), nullable=False)
    session_string = Column(Text, nullable=True)  # Telethon StringSession
    status = Column(SAEnum(AccountStatus), default=AccountStatus.ACTIVE)
    messages_sent = Column(Integer, default=0)
    flood_wait_until = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="accounts")


class Campaign(Base):
    """Mailing campaign"""
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)
    message_text = Column(Text, nullable=False)
    media_file_id = Column(String(256), nullable=True)  # photo/video file_id
    target_groups = Column(Text, nullable=False)  # JSON list of group usernames/ids
    messages_to_send = Column(Integer, nullable=False)
    messages_sent = Column(Integer, default=0)
    messages_failed = Column(Integer, default=0)
    status = Column(SAEnum(CampaignStatus), default=CampaignStatus.DRAFT)
    delay_seconds = Column(Float, default=2.5)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="campaigns")
    logs = relationship("CampaignLog", back_populates="campaign", cascade="all, delete-orphan")


class CampaignLog(Base):
    """Per-message delivery log"""
    __tablename__ = "campaign_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    group_target = Column(String(256), nullable=False)
    account_phone = Column(String(20), nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(String(512), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="logs")


class Payment(Base):
    """Payment records"""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_key = Column(String(32), nullable=False)  # e.g. "pro", "monthly"
    plan_type = Column(String(16), nullable=False)  # "package" or "subscription"
    amount_usd = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)  # USDT, TON, BTC, etc.
    invoice_id = Column(String(128), unique=True, nullable=True)  # CryptoBot invoice ID
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    messages_credited = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")


# ─── DB Setup ──────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
