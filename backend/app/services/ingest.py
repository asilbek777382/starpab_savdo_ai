"""Kiruvchi xabarlarni (Telegram, Instagram) saqlash va AI javobini navbatga qo'yish."""

import logging
import uuid
from dataclasses import dataclass

from aiogram.types import Message as TgMessage
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


@dataclass
class Sender:
    """Kanaldan mustaqil mijoz ma'lumoti (Telegram user yoki Instagram IGSID)."""

    user_id: int
    chat_id: int
    name: str | None = None
    username: str | None = None
    language: str | None = None


def tg_sender(user, chat_id: int) -> Sender:
    return Sender(user.id, chat_id, user.full_name, user.username, user.language_code)


async def get_or_create_customer(session: AsyncSession, channel: Channel, sender: Sender) -> Customer:
    customer = await session.scalar(
        select(Customer).where(
            Customer.shop_id == channel.shop_id,
            Customer.channel_id == channel.id,
            Customer.external_user_id == sender.user_id,
        )
    )
    if customer is None:
        customer = Customer(
            shop_id=channel.shop_id,
            channel_id=channel.id,
            external_user_id=sender.user_id,
            chat_id=sender.chat_id,
            name=sender.name,
            username=sender.username,
            language=sender.language,
        )
        session.add(customer)
        await session.flush()
    else:
        customer.username = sender.username or customer.username
        customer.name = customer.name or sender.name
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


async def ingest_incoming(
    session: AsyncSession,
    rt: Runtime,
    channel: Channel,
    sender: Sender,
    data: Extracted,
    external_message_id: int | None = None,
) -> Conversation | None:
    """Mijoz xabarini saqlaydi. None — rate limit tufayli qabul qilinmadi."""
    s = get_settings()
    if not await customer_allowed(rt.redis, channel.shop_id, sender.user_id, s.customer_msgs_per_minute):
        log.info("Rate limit: shop=%s user=%s", channel.shop_id, sender.user_id)
        return None

    customer = await get_or_create_customer(session, channel, sender)
    conv = await get_open_conversation(session, customer)
    await touch_conversation_window(session, conv)

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
            external_message_id=external_message_id,
        )
    )
    await session.flush()
    return conv


async def ingest_customer_message(
    session: AsyncSession, rt: Runtime, channel: Channel, message: TgMessage
) -> Conversation | None:
    if message.from_user is None:
        return None
    sender = tg_sender(message.from_user, message.chat.id)
    return await ingest_incoming(session, rt, channel, sender, extract(message), message.message_id)


async def record_staff_message(
    session: AsyncSession, channel: Channel, customer_sender: Sender, text: str, external_message_id: int | None = None
) -> None:
    """Sotuvchi o'z akkauntidan mijozga yozdi — xabar saqlanadi va AI shu suhbatda jim turadi."""
    customer = await get_or_create_customer(session, channel, customer_sender)
    conv = await get_open_conversation(session, customer)
    settings = await session.get(ShopSettings, channel.shop_id)
    mark_staff_takeover(conv, settings, get_settings().default_handoff_silence_minutes)
    session.add(
        Message(
            shop_id=channel.shop_id,
            conversation_id=conv.id,
            role="staff",
            content=text,
            external_message_id=external_message_id,
            answered=True,
        )
    )
    # Sotuvchi javob bergan — kutib turgan mijoz xabarlariga AI endi javob bermaydi
    pending = await session.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.role == "customer", ~Message.answered)
    )
    for m in pending:
        m.answered = True


async def ingest_staff_message(session: AsyncSession, channel: Channel, message: TgMessage) -> None:
    chat = message.chat
    sender = Sender(chat.id, chat.id, chat.full_name or chat.title, chat.username)
    text = message.text or message.caption or f"[{message.content_type}]"
    await record_staff_message(session, channel, sender, text, message.message_id)


def debounce_key(conv_id: int) -> str:
    return f"conv:{conv_id}:last"


async def enqueue_reply(rt: Runtime, conv_id: int) -> str:
    """Debounce: har yangi xabar yangi token yozadi; faqat oxirgi tokenli job javob beradi."""
    token = uuid.uuid4().hex
    await rt.redis.set(debounce_key(conv_id), token, ex=3600)
    if rt.arq is not None:
        await rt.arq.enqueue_job("process_conversation", conv_id, token, _defer_by=get_settings().debounce_seconds)
    return token
