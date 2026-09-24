from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import TimestampMixin

# Hujjatdagi tariflar: narx (so'm/oy) va oylik suhbatlar limiti
PLANS: dict[str, dict] = {
    "trial": {"price": 0, "conversations": 300, "max_products": 300, "instagram": True},
    "start": {"price": 149_000, "conversations": 300, "max_products": 300, "instagram": False},
    "business": {"price": 299_000, "conversations": 1_000, "max_products": 5_000, "instagram": True},
    "pro": {"price": 599_000, "conversations": 3_000, "max_products": None, "instagram": True},
}
EXTRA_PACK = {"price": 29_000, "conversations": 100}


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / expired / cancelled


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(20))  # manual / click / payme
    provider_txn_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
