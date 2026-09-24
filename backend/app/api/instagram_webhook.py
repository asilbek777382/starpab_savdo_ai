"""Instagram Direct webhook (Meta): GET — tasdiqlash, POST — xabarlar.

Meta har bir POST'ni X-Hub-Signature-256 (HMAC-SHA256, ilova sirri bilan) bilan imzolaydi.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.instagram.client import InstagramAPI
from app.instagram.outbound import sent_key
from app.models import Channel, Customer
from app.runtime import Runtime, get_runtime
from app.services.crypto import decrypt
from app.services.ingest import Extracted, Sender, enqueue_reply, ingest_incoming, record_staff_message

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

MID_TTL = 24 * 3600


@router.get("/ig/webhook")
async def verify(request: Request) -> Response:
    q = request.query_params
    expected = get_settings().ig_verify_token
    if expected and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), expected):
        return PlainTextResponse(q.get("hub.challenge", ""))
    return Response(status_code=403)


def signature_ok(body: bytes, header: str) -> bool:
    secret = get_settings().ig_app_secret
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def extract_message(msg: dict) -> Extracted:
    text = (msg.get("text") or "").strip()
    media = {"mid": msg.get("mid")}
    notes = []
    for att in msg.get("attachments") or []:
        kind = att.get("type")
        url = (att.get("payload") or {}).get("url")
        if kind == "image":
            notes.append("[Rasm yubordi]")
            media.update(type="photo", url=url)
        elif kind == "audio":
            media.update(type="voice", url=url)
        elif kind == "video":
            notes.append("[Video yubordi]")
        elif kind in ("share", "ig_reel", "reel"):
            notes.append("[Post ulashdi]")
        elif kind == "story_mention":
            notes.append("[Storyda belgiladi]")
        else:
            notes.append(f"[{kind} yubordi]")
    if (msg.get("reply_to") or {}).get("story"):
        notes.insert(0, "[Storyga javob]")
    return Extracted(text=" ".join([*notes, text]).strip(), media=media)


async def _fill_profile(session: AsyncSession, channel: Channel, sender_id: int) -> None:
    """Yangi mijozning ismi va @username'ini olishga urinadi (bo'lmasa ham davom etadi)."""
    customer = await session.scalar(
        select(Customer).where(Customer.channel_id == channel.id, Customer.external_user_id == sender_id)
    )
    token = decrypt(channel.token_encrypted)
    if customer is None or customer.name or not token:
        return
    try:
        profile = await InstagramAPI(token, channel.external_id).user_profile(str(sender_id))
    except Exception:  # noqa: BLE001
        log.debug("Instagram profili olinmadi", exc_info=True)
        return
    customer.name = profile.get("name") or profile.get("username")
    customer.username = profile.get("username")


async def handle_event(session: AsyncSession, rt: Runtime, channel: Channel, event: dict) -> int | None:
    """Bitta messaging hodisasi. Javob kerak bo'lsa suhbat id'sini qaytaradi."""
    msg = event.get("message")
    if not msg or msg.get("is_deleted") or msg.get("is_unsupported"):
        return None
    mid = msg.get("mid")
    if mid and not await rt.redis.set(f"ig:mid:{mid}", 1, nx=True, ex=MID_TTL):
        return None  # takroriy yetkazish
    if msg.get("is_echo"):
        if mid and await rt.redis.exists(sent_key(mid)):
            return None  # o'zimiz yuborgan javob
        # Sotuvchi Instagram ilovasidan o'zi yozdi — AI shu suhbatda jim turadi
        customer_id = int(event["recipient"]["id"])
        await record_staff_message(session, channel, Sender(customer_id, customer_id), msg.get("text") or "[media]")
        return None
    sender_id = int(event["sender"]["id"])
    if str(sender_id) == channel.external_id:
        return None
    conv = await ingest_incoming(session, rt, channel, Sender(sender_id, sender_id), extract_message(msg))
    if conv is None:
        return None
    await _fill_profile(session, channel, sender_id)
    return conv.id


@router.post("/ig/webhook", response_model=None)
async def receive(request: Request) -> Response | dict:
    body = await request.body()
    if not signature_ok(body, request.headers.get("x-hub-signature-256", "")):
        return Response(status_code=403)
    try:
        data = await request.json()
    except ValueError:
        return {"ok": True}
    if data.get("object") != "instagram":
        return {"ok": True}
    rt = get_runtime()
    to_reply: list[int] = []
    async with get_sessionmaker()() as session:
        for entry in data.get("entry") or []:
            channel = await session.scalar(
                select(Channel).where(
                    Channel.type == "instagram", Channel.external_id == str(entry.get("id")), Channel.is_enabled
                )
            )
            if channel is None:
                log.info("Instagram: noma'lum akkaunt %s", entry.get("id"))
                continue
            for event in entry.get("messaging") or []:
                try:
                    async with session.begin_nested():  # bitta hodisa xatosi boshqalarini buzmasin
                        conv_id = await handle_event(session, rt, channel, event)
                except Exception:
                    # Meta qayta-qayta yubormasligi uchun 200 qaytaramiz; xato logda
                    log.exception("Instagram hodisasi qayta ishlanmadi")
                    continue
                if conv_id:
                    to_reply.append(conv_id)
        await session.commit()
    for conv_id in dict.fromkeys(to_reply):
        await enqueue_reply(rt, conv_id)
    return {"ok": True}
