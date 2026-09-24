from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
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
# Yillik to'lovga chegirma (hujjat: 20%)
YEARLY_DISCOUNT = 0.20


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / expired / cancelled


class Payment(TimestampMixin, Base):
    """Obuna to'lovi. Onlayn to'lovda bu yozuv hisob-faktura vazifasini ham bajaradi:
    uning id'si Payme'da account.order_id, Click'da merchant_trans_id bo'ladi."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # so'm
    provider: Mapped[str] = mapped_column(String(20))  # manual / click / payme / card
    provider_txn_id: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / paid / cancelled
    plan: Mapped[str | None] = mapped_column(String(20))
    months: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Provayder tranzaksiya holati (Payme: 1, 2, -1, -2) va vaqtlari
    state: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    provider_create_time: Mapped[int | None] = mapped_column(BigInteger)  # ms (Payme "time")
    perform_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[int | None] = mapped_column(Integer)
