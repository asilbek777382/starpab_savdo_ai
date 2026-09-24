"""Kiruvchi Telegram xabarlarini saqlash va AI javobini navbatga qo'yish."""

import logging
import uuid
from dataclasses import dataclass

from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.masking import PhoneMasker
from app.config import get_settings
from app.models import Channel, Conversation, Customer, Message, ShopSettings
from app.runtime import Runtime
from app.services.handoff import mark_staff_takeover
from app.services.ratelimit import customer_allowed
from app.services.usage import touch_conversation_window

log = logging.getLogger(__name__)


@dataclass
class Extracted:
    text: str
    media: dict | None = None
    location: dict | None = None
    phone: str | None = None


def extract(message: TgMessage) -> Extracted:
    text = message.text or message.caption or ""
    if message.voice:
        return Extracted(text=text, media={"type": "voice", "file_id": message.voice.file_id})
    if message.location:
        loc = {"latitude": message.location.latitude, "longitude": message.location.longitude}
        return Extracted(text=f"[Lokatsiya yubordi: {loc['latitude']:.5f}, {loc['longitude']:.5f}]", location=loc)
    if message.contact:
        return Extracted(text=f"[Kontakt yubordi: {message.contact.phone_number}]", phone=message.contact.phone_number)
    if message.photo:
        return Extracted(
            text=f"[Rasm yubordi] {text}".strip(), media={"type": "photo", "file_id": message.photo[-1].file_id}
        )
    if not text:
        kind = message.content_type
        return Extracted(text=f"[{kind} yubordi]")
    return Extracted(text=text)


async def get_or_create_customer(session: AsyncSession, channel: Channel, user: TgUser, chat_id: int) -> Customer:
    customer = await session.scalar(
        select(Customer).where(
            Customer.shop_id == channel.shop_id,
            Customer.channel_id == channel.id,
            Customer.external_user_id == user.id,
        )
    )
    if customer is None:
        customer = Customer(
            shop_id=channel.shop_id,
            channel_id=channel.id,
            external_user_id=user.id,
            chat_id=chat_id,
            name=user.full_name,
            username=user.username,
            language=user.language_code,
        )
        session.add(customer)
        await session.flush()
    else:
        customer.username = user.username or customer.username
    return customer


async def get_open_conversation(session: AsyncSession, customer: Customer) -> Conversation:
    conv = await session.scalar(
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(Conversation.id.desc())
        .limit(1)
        .with_for_update()
    )
    if conv is None:
        conv = Conversation(
            shop_id=customer.shop_id,
            customer_id=customer.id,
            channel_id=customer.channel_id,
            cart=[],
            contact={},
        )
        session.add(conv)
        await session.flush()
    elif conv.status == "closed":
        conv.status = "ai"
        conv.stage = "greeting"
    return conv


async def ingest_customer_message(
    session: AsyncSession, rt: Runtime, channel: Channel, message: TgMessage
) -> Conversation | None:
    s = get_settings()
    user = message.from_user
    if user is None:
        return None
    if not await customer_allowed(rt.redis, channel.shop_id, user.id, s.customer_msgs_per_minute):
        log.info("Rate limit: shop=%s user=%s", channel.shop_id, user.id)
        return None

    customer = await get_or_create_customer(session, channel, user, message.chat.id)
    conv = await get_open_conversation(session, customer)
    await touch_conversation_window(session, conv)

    data = extract(message)
    contact = dict(conv.contact or {})
    if data.location:
        contact["location"] = data.location
    if data.phone:
        masker = PhoneMasker(contact.get("phones"))
        masker.add(data.phone)
        contact["phones"] = masker.phones
        customer.phone = customer.phone or data.phone
    conv.contact = contact

    session.add(
        Message(
            shop_id=channel.shop_id,
            conversation_id=conv.id,
            role="customer",
            content=data.text,
            media=data.media,
            external_message_id=message.message_id,
        )
    )
    await session.flush()
    return conv


async def ingest_staff_message(session: AsyncSession, channel: Channel, message: TgMessage) -> None:
    """Sotuvchi o'z akkauntidan mijozga yozdi — xabar saqlanadi va AI shu suhbatda jim turadi."""
    chat = message.chat
    fake_user = TgUser(id=chat.id, is_bot=False, first_name=chat.first_name or chat.title or "", username=chat.username)
    customer = await get_or_create_customer(session, channel, fake_user, chat.id)
    conv = await get_open_conversation(session, customer)
    settings = await session.get(ShopSettings, channel.shop_id)
    mark_staff_takeover(conv, settings, get_settings().default_handoff_silence_minutes)
    session.add(
        Message(
            shop_id=channel.shop_id,
            conversation_id=conv.id,
            role="staff",
            content=message.text or message.caption or f"[{message.content_type}]",
            external_message_id=message.message_id,
            answered=True,
        )
    )
    # Sotuvchi javob bergan — kutib turgan mijoz xabarlariga AI endi javob bermaydi
    pending = await session.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.role == "customer", ~Message.answered)
    )
    for m in pending:
        m.answered = True


def debounce_key(conv_id: int) -> str:
    return f"conv:{conv_id}:last"


async def enqueue_reply(rt: Runtime, conv_id: int) -> str:
    """Debounce: har yangi xabar yangi token yozadi; faqat oxirgi tokenli job javob beradi."""
    token = uuid.uuid4().hex
    await rt.redis.set(debounce_key(conv_id), token, ex=3600)
    if rt.arq is not None:
        await rt.arq.enqueue_job("process_conversation", conv_id, token, _defer_by=get_settings().debounce_seconds)
    return token
