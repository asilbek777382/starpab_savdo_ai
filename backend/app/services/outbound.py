"""Mijozga javob kanalini tanlash: Telegram (Business yoki bot) yoki Instagram Direct."""

from datetime import UTC, datetime, timedelta

from app.instagram.client import InstagramAPI
from app.instagram.outbound import InstagramOutbound
from app.models import Channel, Conversation, Customer
from app.runtime import Runtime
from app.services.crypto import decrypt
from app.telegram.outbound import Outbound, TelegramOutbound

# Instagram: mijozning oxirgi xabaridan keyin faqat 24 soat ichida yozish mumkin (zaxira bilan)
INSTAGRAM_WINDOW = timedelta(hours=23, minutes=50)


def build_outbound(rt: Runtime, channel: Channel, customer: Customer) -> Outbound | None:
    if channel.type in ("tg_business", "tg_bot"):
        if rt.bot is None:
            return None
        bcid = channel.business_connection_id if channel.type == "tg_business" else None
        return TelegramOutbound(rt.bot, customer.chat_id, bcid)
    if channel.type == "instagram":
        token = decrypt(channel.token_encrypted)
        if not token:
            return None
        return InstagramOutbound(InstagramAPI(token, channel.external_id), str(customer.external_user_id), rt.redis)
    return None


def within_messaging_window(channel: Channel, conv: Conversation | None) -> bool:
    if channel.type != "instagram":
        return True
    last = conv.last_message_at if conv else None
    return last is not None and datetime.now(UTC) - last < INSTAGRAM_WINDOW
