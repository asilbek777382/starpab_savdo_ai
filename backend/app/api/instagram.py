"""Instagram professional akkauntini do'konga ulash (Business Login for Instagram)."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, owner_only
from app.config import get_settings
from app.db import get_session
from app.instagram import client as ig
from app.models import PLANS, Channel
from app.runtime import get_runtime
from app.schemas.api import LinkOut
from app.services.auth import consume_token, issue_token, web_url
from app.services.crypto import encrypt

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/instagram", tags=["instagram"])

STATE_TTL = 10 * 60


def instagram_configured() -> bool:
    s = get_settings()
    return bool(s.ig_app_id and s.ig_app_secret)


@router.post("/connect", response_model=LinkOut)
async def connect(user: CurrentUser = Depends(owner_only)) -> LinkOut:
    if not instagram_configured():
        raise HTTPException(503, "Instagram ulanishi hali sozlanmagan (platforma administratori)")
    if not PLANS.get(user.shop.plan, PLANS["start"]).get("instagram"):
        raise HTTPException(402, "Instagram Biznes tarifidan boshlab ulanadi")
    state = await issue_token(get_runtime().redis, "igstate", str(user.shop.id), STATE_TTL)
    return LinkOut(url=ig.authorize_url(state), expires_in=STATE_TTL)


def _back(status: str) -> RedirectResponse:
    return RedirectResponse(web_url(f"/app/connect?instagram={status}"), status_code=302)


@router.get("/callback", include_in_schema=False)
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    shop_id = await consume_token(get_runtime().redis, "igstate", state) if state else None
    if shop_id is None or error or not code:
        return _back("error")
    try:
        short = await ig.exchange_code(code.removesuffix("#_"))
        token = await ig.long_lived_token(short)
        api = ig.InstagramAPI(token.access_token)
        me = await api.me()
        account_id = str(me.get("user_id") or me["id"])
        await api.subscribe_messages()
    except (ig.InstagramError, KeyError):
        log.exception("Instagram ulanmadi")
        return _back("error")

    other = await session.scalar(
        select(Channel).where(
            Channel.type == "instagram",
            Channel.external_id == account_id,
            Channel.is_enabled,
            Channel.shop_id != int(shop_id),
        )
    )
    if other is not None:
        return _back("taken")
    channel = await session.scalar(select(Channel).where(Channel.shop_id == int(shop_id), Channel.type == "instagram"))
    if channel is None:
        channel = Channel(shop_id=int(shop_id), type="instagram")
        session.add(channel)
    channel.external_id = account_id
    channel.display_name = f"@{me['username']}" if me.get("username") else None
    channel.token_encrypted = encrypt(token.access_token)
    channel.token_expires_at = token.expires_at
    channel.can_reply = True
    channel.is_enabled = True
    await session.commit()
    return _back("ok")


@router.delete("", status_code=204)
async def disconnect(user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)) -> None:
    channel = await session.scalar(select(Channel).where(Channel.shop_id == user.shop.id, Channel.type == "instagram"))
    if channel is not None:
        channel.is_enabled = False
        channel.token_encrypted = None
        channel.token_expires_at = datetime.now(UTC)
        await session.commit()
