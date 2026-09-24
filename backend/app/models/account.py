from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import TimestampMixin


class Account(TimestampMixin, Base):
    """Web panelga kirish uchun akkaunt (telefon + parol). Bitta akkaunt bir nechta do'konga ega bo'lishi mumkin."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # +998XXXXXXXXX; Telegram orqali (magic link) yaratilgan akkauntda hali bo'lmasligi mumkin
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200), default="")
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    lang: Mapped[str] = mapped_column(String(5), default="uz")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
