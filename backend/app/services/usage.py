"""Tarif limitlari va oylik foydalanish hisobi. "Suhbat" = mijoz bilan 24 soat ichidagi yozishma."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PLANS, Conversation, Shop, Subscription, UsageCounter

WINDOW = timedelta(hours=24)


def period_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


async def _bump(session: AsyncSession, shop_id: int, conversations: int = 0, tokens: int = 0, cost=0) -> None:
    stmt = insert(UsageCounter).values(
        shop_id=shop_id, period=period_key(), conversations=conversations, tokens=tokens, cost=Decimal(cost)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UsageCounter.shop_id, UsageCounter.period],
        set_={
            "conversations": UsageCounter.conversations + stmt.excluded.conversations,
            "tokens": UsageCounter.tokens + stmt.excluded.tokens,
            "cost": UsageCounter.cost + stmt.excluded.cost,
        },
    )
    await session.execute(stmt)


async def touch_conversation_window(session: AsyncSession, conv: Conversation) -> bool:
    """Yangi 24 soatlik oyna boshlansa, oylik suhbatlar hisobiga qo'shiladi."""
    now = datetime.now(UTC)
    conv.last_message_at = now
    if conv.window_started_at is None or now - conv.window_started_at >= WINDOW:
        conv.window_started_at = now
        await _bump(session, conv.shop_id, conversations=1)
        return True
    return False


async def add_usage(session: AsyncSession, shop_id: int, tokens: int, cost: Decimal) -> None:
    await _bump(session, shop_id, tokens=tokens, cost=cost)


async def current_usage(session: AsyncSession, shop_id: int) -> UsageCounter | None:
    return await session.scalar(
        select(UsageCounter).where(UsageCounter.shop_id == shop_id, UsageCounter.period == period_key())
    )


async def check_limits(session: AsyncSession, shop: Shop) -> tuple[bool, str | None]:
    """AI javob bera oladimi? (ruxsat, sabab)."""
    now = datetime.now(UTC)
    if shop.status != "active":
        return False, "paused"
    if shop.plan == "trial":
        if shop.trial_ends_at and shop.trial_ends_at < now:
            return False, "trial_expired"
    else:
        sub = await session.scalar(
            select(Subscription).where(
                Subscription.shop_id == shop.id, Subscription.status == "active", Subscription.period_end > now
            )
        )
        if sub is None:
            return False, "subscription_expired"
    usage = await current_usage(session, shop.id)
    limit = PLANS.get(shop.plan, PLANS["start"])["conversations"] + (shop.extra_conversations or 0)
    if usage and usage.conversations > limit:
        return False, "limit_reached"
    return True, None


LIMIT_MESSAGES = {
    "paused": "Do'kon uchun Navbatchi AI to'xtatilgan.",
    "trial_expired": "14 kunlik bepul sinov muddati tugadi. Navbatchi AI javob bermayapti — tarifni faollashtiring.",
    "subscription_expired": "Obuna muddati tugadi. Navbatchi AI javob bermayapti — to'lovni amalga oshiring.",
    "limit_reached": "Bu oy uchun suhbatlar limiti tugadi. Qo'shimcha paket (+100 suhbat) yoki yuqoriroq tarif oling.",
}
