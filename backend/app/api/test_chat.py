"""Sotuvchi AI'ni Telegram'siz sinab ko'rishi uchun test chat. Eval ham shu yo'ldan foydalanadi."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.turn import NullNotifier
from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import Conversation, Customer, Message
from app.runtime import get_runtime
from app.schemas.api import TestChatIn, TestChatOut
from app.services.conversation import reply_to_conversation
from app.services.shops import get_channel
from app.services.usage import touch_conversation_window
from app.telegram.notify import TelegramNotifier
from app.telegram.outbound import RecordingOutbound

router = APIRouter(prefix="/api/test-chat", tags=["test-chat"])


@router.post("", response_model=TestChatOut)
async def test_chat(
    body: TestChatIn, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> TestChatOut:
    rt = get_runtime()
    shop_id = user.shop.id
    channel = await get_channel(session, shop_id, "test")
    customer = await session.scalar(
        select(Customer).where(Customer.channel_id == channel.id, Customer.external_user_id == user.test_customer_id)
    )
    if customer is None:
        customer = Customer(
            shop_id=shop_id,
            channel_id=channel.id,
            external_user_id=user.test_customer_id,
            chat_id=user.test_customer_id,
            name="Test mijoz",
        )
        session.add(customer)
        await session.flush()
    conv = await session.scalar(
        select(Conversation).where(Conversation.customer_id == customer.id).order_by(Conversation.id.desc()).limit(1)
    )
    if conv is None or body.reset:
        conv = Conversation(shop_id=shop_id, customer_id=customer.id, channel_id=channel.id, cart=[], contact={})
        session.add(conv)
        await session.flush()
    await touch_conversation_window(session, conv)
    media = {"type": "voice", "transcribed": True} if body.as_voice else None
    session.add(Message(shop_id=shop_id, conversation_id=conv.id, role="customer", content=body.message, media=media))
    await session.commit()

    outbound = RecordingOutbound()
    notifier = TelegramNotifier(rt.bot, session, shop_id) if rt.bot is not None else NullNotifier()
    result = await reply_to_conversation(
        session, rt, conv.id, outbound=outbound, notifier=notifier, check_billing=False
    )
    return TestChatOut(
        status=result.status,
        replies=outbound.sent,
        order_number=result.order_number,
        lead_id=result.lead_id,
        voice=result.voice,
        handed_off=result.handed_off,
        tools=result.tools,
    )
