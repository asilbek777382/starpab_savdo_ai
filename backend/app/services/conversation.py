"""Suhbatga AI javobini tayyorlash va yuborish. Worker ham, test chat ham shu funksiyadan foydalanadi."""

import asyncio
import base64
import contextlib
import io
import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import run_turn
from app.ai.masking import PhoneMasker
from app.ai.turn import Notifier, NullNotifier, TurnContext
from app.config import get_settings
from app.models import Channel, Conversation, Customer, Message, Shop, ShopSettings
from app.runtime import Runtime
from app.services.handoff import ai_may_reply, handoff_event, handoff_reply_for, mark_handoff, wants_human
from app.services.outbound import build_outbound
from app.services.ratelimit import add_shop_tokens, shop_tokens_today
from app.services.stt import transcribe
from app.services.tts import should_speak
from app.services.usage import LIMIT_MESSAGES, add_usage, check_limits
from app.telegram.notify import TelegramNotifier, notify_shop
from app.telegram.outbound import Outbound

log = logging.getLogger(__name__)

VOICE_FAILED = "[Ovozli xabar — matnga aylantirib bo'lmadi. Mijozdan matn bilan yozishini so'ra.]"


@dataclass
class ReplyResult:
    status: str
    text: str = ""
    order_number: int | None = None
    lead_id: int | None = None
    voice: bool = False
    handed_off: bool = False
    tools: list[dict] = field(default_factory=list)


async def _typing_loop(outbound: Outbound) -> None:
    while True:
        await outbound.send_typing()
        await asyncio.sleep(4)


MAX_IMAGES = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024


async def _download_media(rt: Runtime, media: dict) -> bytes | None:
    """Telegram: file_id orqali; Instagram: attachment URL orqali."""
    if media.get("url"):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media["url"])
            resp.raise_for_status()
            return resp.content
    if media.get("file_id") and rt.bot is not None:
        buf = io.BytesIO()
        await rt.bot.download(media["file_id"], destination=buf)
        return buf.getvalue()
    return None


def _image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return None


async def _collect_images(rt: Runtime, pending: list[Message]) -> list[dict]:
    """Mijoz shu navbatda yuborgan rasmlarni AI ko'rishi uchun image bloklariga aylantiradi."""
    blocks: list[dict] = []
    for msg in pending:
        if len(blocks) >= MAX_IMAGES:
            break
        if not (msg.media and msg.media.get("type") == "photo"):
            continue
        try:
            data = await _download_media(rt, msg.media)
        except Exception:  # noqa: BLE001 — rasm yuklanmasa, matn bilan davom etamiz
            log.warning("Mijoz rasmi yuklanmadi", exc_info=True)
            continue
        media_type = _image_type(data or b"")
        if not data or media_type is None or len(data) > MAX_IMAGE_BYTES:
            continue
        blocks.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()},
            }
        )
    return blocks


async def _transcribe_voices(rt: Runtime, pending: list[Message]) -> None:
    for msg in pending:
        if not (msg.media and msg.media.get("type") == "voice") or msg.media.get("transcribed"):
            continue
        text = None
        try:
            audio = await _download_media(rt, msg.media)
            if audio:
                text = await transcribe(audio)
        except Exception:  # noqa: BLE001
            log.warning("Ovozli xabar yuklanmadi", exc_info=True)
        msg.content = f"{msg.content}\n{text}".strip() if text else (msg.content or VOICE_FAILED)
        msg.media = {**msg.media, "transcribed": bool(text)}


async def _warn_once(rt: Runtime, session: AsyncSession, shop_id: int, reason: str) -> None:
    if rt.bot is None:
        return
    if await rt.redis.set(f"warn:{shop_id}:{reason}", 1, nx=True, ex=24 * 3600):
        await notify_shop(rt.bot, session, shop_id, "⚠️ " + LIMIT_MESSAGES.get(reason, reason))


async def reply_to_conversation(
    session: AsyncSession,
    rt: Runtime,
    conv_id: int,
    *,
    outbound: Outbound | None = None,
    notifier: Notifier | None = None,
    check_billing: bool = True,
) -> ReplyResult:
    s = get_settings()
    conv = await session.get(Conversation, conv_id, with_for_update=True)
    if conv is None:
        return ReplyResult("missing")
    shop = await session.get(Shop, conv.shop_id)
    settings = await session.get(ShopSettings, conv.shop_id)
    customer = await session.get(Customer, conv.customer_id)
    channel = await session.get(Channel, conv.channel_id)

    pending = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id, Message.role == "customer", ~Message.answered)
            .order_by(Message.id)
        )
    )
    if not pending:
        return ReplyResult("nothing")

    def mark_answered() -> None:
        for m in pending:
            m.answered = True

    if not settings.ai_enabled or not channel.is_enabled or not ai_may_reply(conv):
        mark_answered()  # bu xabarlarga odam javob beradi
        await session.commit()
        return ReplyResult("ai_off")
    if check_billing:
        ok, reason = await check_limits(session, shop)
        if not ok:
            mark_answered()
            await session.commit()
            await _warn_once(rt, session, shop.id, reason)
            return ReplyResult(f"blocked:{reason}")
        if await shop_tokens_today(rt.redis, shop.id) > s.shop_daily_token_limit:
            mark_answered()
            await session.commit()
            await _warn_once(rt, session, shop.id, "daily_tokens")
            return ReplyResult("blocked:daily_tokens")
    if channel.type == "tg_business" and not channel.can_reply:
        return ReplyResult("cannot_reply")

    if outbound is None:
        outbound = build_outbound(rt, channel, customer)
        if outbound is None:
            return ReplyResult("no_outbound")
    if notifier is None:
        notifier = TelegramNotifier(rt.bot, session, shop.id) if rt.bot is not None else NullNotifier()

    await _transcribe_voices(rt, pending)
    upto_id = pending[-1].id
    customer_text = "\n".join(m.content or "" for m in pending)

    # Odam so'ralgan bo'lsa — LLM'ni chaqirmasdan uzatamiz
    if wants_human(customer_text, (settings.handoff_rules or {}).get("keywords")):
        reason = f"Mijoz yozdi: {customer_text[:200]}"
        mark_handoff(conv, settings)
        session.add(handoff_event(conv, reason))
        await notifier.handoff(conv, customer, reason)
        text = handoff_reply_for(customer_text)
        ext_id = await _safe_send(outbound, text)
        session.add(
            Message(
                shop_id=shop.id,
                conversation_id=conv.id,
                role="ai",
                content=text,
                external_message_id=ext_id,
                answered=True,
            )
        )
        mark_answered()
        await session.commit()
        await notifier.flush()
        return ReplyResult("handoff", text=text, handed_off=True)

    masker = PhoneMasker((conv.contact or {}).get("phones"))
    ctx = TurnContext(
        session=session,
        shop=shop,
        settings=settings,
        conv=conv,
        customer=customer,
        channel=channel,
        outbound=outbound,
        notifier=notifier,
        masker=masker,
        embedder=rt.embedder,
        order_source="test" if channel.type == "test" else "ai",
        images=await _collect_images(rt, pending),
    )
    typing = asyncio.create_task(_typing_loop(outbound))
    try:
        result = await run_turn(ctx, rt.llm, upto_id=upto_id)
    finally:
        typing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing

    conv.contact = {**(conv.contact or {}), "phones": masker.phones}
    customer_sent_voice = any(m.media and m.media.get("type") == "voice" for m in pending)
    voice_sent = False
    if result.text and not result.llm_failed and should_speak(settings.voice_mode, customer_sent_voice):
        voice_sent = await _send_voice(rt, outbound, result.text, settings.voice_gender)
    ext_id = await _safe_send(outbound, result.text) if result.text else None
    session.add(
        Message(
            shop_id=shop.id,
            conversation_id=conv.id,
            role="ai",
            content=result.text,
            media={"type": "voice_reply"} if voice_sent else None,
            external_message_id=ext_id,
            answered=True,
            tokens_in=result.usage.total_in,
            tokens_out=result.usage.output_tokens,
            cost=result.cost,
        )
    )
    mark_answered()
    tokens = result.usage.total_in + result.usage.output_tokens
    await add_usage(session, shop.id, tokens, result.cost)
    await session.commit()
    await add_shop_tokens(rt.redis, shop.id, tokens)
    await notifier.flush()
    return ReplyResult(
        "llm_failed" if result.llm_failed else "replied",
        text=result.text,
        order_number=ctx.order.number if ctx.order else None,
        lead_id=ctx.lead.id if ctx.lead else None,
        voice=voice_sent,
        handed_off=ctx.handed_off,
        tools=ctx.tool_log,
    )


async def _send_voice(rt: Runtime, outbound: Outbound, text: str, gender: str) -> bool:
    """Javobni ovozli xabar qilib yuboradi. Kanal ovozni qo'llamasa yoki TTS ishlamasa — False (matn baribir ketadi)."""
    send_voice = getattr(outbound, "send_voice", None)
    if rt.tts is None or send_voice is None or len(text) > get_settings().tts_max_chars:
        return False
    try:
        audio = await rt.tts.synthesize(text, gender)
        if not audio:
            return False
        await send_voice(audio)
        return True
    except Exception:  # noqa: BLE001 — ovoz qo'shimcha; matnli javob to'xtamasligi kerak
        log.warning("Ovozli javob yuborilmadi", exc_info=True)
        return False


async def _safe_send(outbound: Outbound, text: str) -> int | None:
    try:
        return await outbound.send_text(text)
    except Exception:  # noqa: BLE001 — javob yuborilmasa ham suhbat holati saqlanadi
        log.exception("Mijozga javob yuborilmadi")
        return None
