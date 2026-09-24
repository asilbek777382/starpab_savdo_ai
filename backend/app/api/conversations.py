from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import Conversation, Customer, Message
from app.schemas.api import AIToggleIn, ConversationOut, MessageOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def _get_conv(session: AsyncSession, shop_id: int, conv_id: int) -> Conversation:
    conv = await session.scalar(select(Conversation).where(Conversation.shop_id == shop_id, Conversation.id == conv_id))
    if conv is None:
        raise HTTPException(404)
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Conversation, Customer.name)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Conversation.shop_id == user.shop.id)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(min(limit, 200))
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Conversation.status == status)
    out = []
    for conv, name in await session.execute(stmt):
        item = ConversationOut.model_validate(conv)
        item.customer_name = name
        out.append(item)
    return out


@router.get("/{conv_id}/messages", response_model=list[MessageOut])
async def conversation_messages(
    conv_id: int, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    await _get_conv(session, user.shop.id, conv_id)
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conv_id, Message.role.in_(("customer", "ai", "staff")))
        .order_by(Message.id)
    )
    return [MessageOut.model_validate(m) for m in rows]


@router.post("/{conv_id}/ai", response_model=ConversationOut)
async def toggle_ai(
    conv_id: int,
    body: AIToggleIn,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """ "Men o'zim javob beraman": AI'ni shu suhbatda to'xtatish (minutes berilmasa — muddatsiz)."""
    conv = await _get_conv(session, user.shop.id, conv_id)
    if body.enabled:
        conv.status, conv.human_until = "ai", None
        if conv.stage == "handoff":
            conv.stage = "discovery"
    else:
        conv.status = "human"
        conv.human_until = datetime.now(UTC) + timedelta(minutes=body.minutes) if body.minutes else None
    await session.commit()
    return ConversationOut.model_validate(conv)
