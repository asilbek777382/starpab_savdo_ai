"""Lid: AI mijozdan olgan telefon raqami va qiziqishi. Operatorga Telegram orqali yuboriladi."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Conversation, Customer, Lead, ShopSettings
from app.services.handoff import mark_handoff

DEDUP_WINDOW = timedelta(hours=24)


async def save_lead(
    session: AsyncSession,
    *,
    conv: Conversation,
    customer: Customer,
    channel: Channel,
    settings: ShopSettings,
    phone: str,
    name: str | None,
    interest: str,
    note: str | None = None,
) -> tuple[Lead, bool]:
    """Qaytaradi: (lid, yangi_mi). Bir suhbatda 24 soat ichida o'sha raqam qayta berilsa, lid yangilanadi."""
    since = datetime.now(UTC) - DEDUP_WINDOW
    lead = await session.scalar(
        select(Lead).where(Lead.conversation_id == conv.id, Lead.phone == phone, Lead.created_at >= since)
    )
    created = lead is None
    if lead is None:
        lead = Lead(
            shop_id=conv.shop_id,
            customer_id=customer.id,
            conversation_id=conv.id,
            channel_type=channel.type,
            phone=phone,
        )
        session.add(lead)
    lead.name = name or lead.name or customer.name
    lead.interest = interest or lead.interest
    lead.note = note or lead.note
    customer.phone = phone
    if name and not customer.name:
        customer.name = name
    conv.stage = "lead_captured"
    if settings.handoff_after_lead:
        mark_handoff(conv, settings)
        conv.stage = "lead_captured"
    await session.flush()
    return lead, created
