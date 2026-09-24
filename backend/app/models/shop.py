from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import TimestampMixin


class Shop(TimestampMixin, Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50), default="other")  # clothes, cosmetics, electronics...
    language_default: Mapped[str] = mapped_column(String(10), default="uz")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Tashkent")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / paused
    plan: Mapped[str] = mapped_column(String(20), default="trial")  # trial/start/business/pro
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_conversations: Mapped[int] = mapped_column(Integer, default=0)  # qo'shimcha paketlar
    order_seq: Mapped[int] = mapped_column(Integer, default=0)


class ShopUser(TimestampMixin, Base):
    __tablename__ = "shop_users"
    __table_args__ = (
        UniqueConstraint("shop_id", "telegram_user_id"),
        UniqueConstraint("shop_id", "account_id", name="uq_shop_users_shop_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    # Telegram ulanmagan (saytdan ro'yxatdan o'tgan) xodimda bo'sh bo'ladi — unga bot xabar yubormaydi
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL", name="fk_shop_users_account"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner / staff
    notify: Mapped[bool] = mapped_column(Boolean, default=True)


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # tg_business / tg_bot / instagram
    external_id: Mapped[str | None] = mapped_column(String(100))
    # Business akkaunt egasining Telegram user id'si: undan kelgan xabar = sotuvchi xabari
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger)
    business_connection_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Masalan Instagram @username — panel va xabarnomalarda ko'rsatish uchun
    display_name: Mapped[str | None] = mapped_column(String(200))


class ShopSettings(Base):
    __tablename__ = "shop_settings"

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True)
    faq_text: Mapped[str] = mapped_column(Text, default="")
    rules_text: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    # [{"name": "Toshkent shahri", "keywords": ["toshkent", "chilonzor"], "fee": 20000, "eta": "1 kun"}]
    delivery_zones: Mapped[list] = mapped_column(JSONB, default=list)
    payment_methods: Mapped[str] = mapped_column(Text, default="")
    working_hours: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(50), default="friendly")
    # {"silence_minutes": 30, "allow_discounts": false, "keywords": [...]}
    handoff_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # sell — suhbatdan buyurtmagacha; lead — tanishtirib, telefon raqamini olib operatorga uzatish
    ai_mode: Mapped[str] = mapped_column(String(20), default="sell")
    # Sotuvchi AI'ga yozgan vazifalar/ssenariy (erkin matn)
    ai_tasks: Mapped[str] = mapped_column(Text, default="")
    # Lidlar yuboriladigan Telegram chat/guruh (bo'sh bo'lsa — do'kon xodimlariga)
    lead_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    # Telefon olingandan keyin suhbatni operatorga o'tkazish
    handoff_after_lead: Mapped[bool] = mapped_column(Boolean, default=True)
