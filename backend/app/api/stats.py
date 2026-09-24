from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import PLANS, Channel, Conversation, Message, Order
from app.schemas.api import StatsOut
from app.services.handoff import HANDOFF_EVENT_PREFIX
from app.services.usage import current_usage

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def stats(
    days: int = 30, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> StatsOut:
    shop_id = user.shop.id
    since = datetime.now(UTC) - timedelta(days=days)
    real_channels = select(Channel.id).where(Channel.shop_id == shop_id, Channel.type != "test")

    conversations = await session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.shop_id == shop_id,
            Conversation.last_message_at >= since,
            Conversation.channel_id.in_(real_channels),
        )
    )
    order_filter = (Order.shop_id == shop_id, Order.created_at >= since, Order.source == "ai")
    orders = await session.scalar(select(func.count()).select_from(Order).where(*order_filter))
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(*order_filter, Order.status != "cancelled")
    )
    handoffs = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.shop_id == shop_id,
            Message.role == "system",
            Message.content.startswith(HANDOFF_EVENT_PREFIX),
            Message.created_at >= since,
        )
    )
    cost = await session.scalar(
        select(func.coalesce(func.sum(Message.cost), 0)).where(Message.shop_id == shop_id, Message.created_at >= since)
    )
    usage = await current_usage(session, shop_id)
    conversations = int(conversations or 0)
    return StatsOut(
        days=days,
        conversations=conversations,
        orders=int(orders or 0),
        conversion=round((orders or 0) / conversations, 4) if conversations else 0.0,
        ai_orders_revenue=int(revenue or 0),
        handoffs=int(handoffs or 0),
        ai_cost=Decimal(cost or 0),
        month_conversations=usage.conversations if usage else 0,
        month_limit=PLANS.get(user.shop.plan, PLANS["start"])["conversations"] + (user.shop.extra_conversations or 0),
    )
