"""Mijozga xabar yuborish kanali. Telegram Business'da har bir so'rov business_connection_id bilan ketadi."""

import logging
from typing import Protocol

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.types import InputMediaPhoto

log = logging.getLogger(__name__)


class Outbound(Protocol):
    async def send_text(self, text: str) -> int | None: ...

    async def send_photos(self, photos: list[str], caption: str | None = None) -> list[str | None]: ...

    async def send_typing(self) -> None: ...


class TelegramOutbound:
    supports_telegram_file_ids = True

    def __init__(self, bot: Bot, chat_id: int, business_connection_id: str | None = None) -> None:
        self.bot, self.chat_id, self.bcid = bot, chat_id, business_connection_id

    async def send_text(self, text: str) -> int | None:
        msg = await self.bot.send_message(self.chat_id, text, business_connection_id=self.bcid)
        return msg.message_id

    async def send_photos(self, photos: list[str], caption: str | None = None) -> list[str | None]:
        """photos: URL yoki telegram file_id. Qaytadi: har bir rasmning file_id'si (keshlash uchun)."""
        if not photos:
            return []
        if len(photos) == 1:
            msg = await self.bot.send_photo(self.chat_id, photos[0], caption=caption, business_connection_id=self.bcid)
            return [msg.photo[-1].file_id if msg.photo else None]
        media = [InputMediaPhoto(media=p, caption=caption if i == 0 else None) for i, p in enumerate(photos[:10])]
        msgs = await self.bot.send_media_group(self.chat_id, media, business_connection_id=self.bcid)
        return [m.photo[-1].file_id if m.photo else None for m in msgs]

    async def send_typing(self) -> None:
        try:
            await self.bot.send_chat_action(self.chat_id, ChatAction.TYPING, business_connection_id=self.bcid)
        except Exception:  # noqa: BLE001 — "yozmoqda" holati muhim emas
            log.debug("typing yuborilmadi", exc_info=True)


class RecordingOutbound:
    """Test chat va testlar uchun: yuborilgan hamma narsani yozib boradi."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> int | None:
        self.sent.append({"type": "text", "text": text})
        return None

    async def send_photos(self, photos: list[str], caption: str | None = None) -> list[str | None]:
        self.sent.append({"type": "photos", "photos": photos, "caption": caption})
        return [None] * len(photos)

    async def send_typing(self) -> None:
        return None
