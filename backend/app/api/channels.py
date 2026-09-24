from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user
from app.api.instagram import instagram_configured
from app.config import get_settings
from app.db import get_session
from app.models import PLANS, Channel, Conversation, Lead, Message, Order
from app.schemas.api import ChannelOut, ChannelsOut, DailyPoint
from app.telegram.handlers import bot_link

router = APIRouter(prefix="/api", tags=["channels"])
LOCAL_TZ = "Asia/Tashkent"


@router.get("/channels", response_model=ChannelsOut)
async def channels(user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = list(await session.scalars(select(Channel).where(Channel.shop_id == user.shop.id, Channel.type != "test")))
    instagram = next((c for c in rows if c.type == "instagram" and c.is_enabled), None)
    return ChannelsOut(
        channels=[ChannelOut.model_validate(c) for c in rows],
        bot_username=get_settings().bot_username,
        bot_link=bot_link(user.shop.id),
        business_connected=any(c.type == "tg_business" and c.is_enabled and c.can_reply for c in rows),
        instagram_configured=instagram_configured(),
        instagram_allowed=bool(PLANS.get(user.shop.plan, PLANS["start"]).get("instagram")),
        instagram=ChannelOut.model_validate(instagram) if instagram else None,
    )


def _local_day(column):
    return cast(func.timezone(LOCAL_TZ, column), Date)


@router.get("/stats/daily", response_model=list[DailyPoint])
async def daily_stats(
    days: int = 30, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    days = max(1, min(days, 180))
    shop_id = user.shop.id
    since = datetime.now(UTC) - timedelta(days=days)
    real_channels = select(Channel.id).where(Channel.shop_id == shop_id, Channel.type != "test")
    conv_rows = await session.execute(
        select(_local_day(Message.created_at).label("d"), func.count(func.distinct(Message.conversation_id)))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.shop_id == shop_id,
            Message.role == "customer",
            Message.created_at >= since,
            Conversation.channel_id.in_(real_channels),
        )
        .group_by("d")
    )
    order_rows = await session.execute(
        select(_local_day(Order.created_at).label("d"), func.count())
        .where(Order.shop_id == shop_id, Order.source == "ai", Order.created_at >= since)
        .group_by("d")
    )
    lead_rows = await session.execute(
        select(_local_day(Lead.created_at).label("d"), func.count())
        .where(Lead.shop_id == shop_id, Lead.channel_type != "test", Lead.created_at >= since)
        .group_by("d")
    )
    convs = {d: n for d, n in conv_rows}
    orders = {d: n for d, n in order_rows}
    leads = {d: n for d, n in lead_rows}
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        out.append(
            DailyPoint(
                date=d.isoformat(), conversations=convs.get(d, 0), orders=orders.get(d, 0), leads=leads.get(d, 0)
            )
        )
    return out
