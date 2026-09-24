"""Mini App autentifikatsiyasi: Telegram WebApp initData HMAC bilan tekshiriladi.

Header: Authorization: tma <initData>. Bir nechta do'koni bo'lsa X-Shop-Id bilan tanlanadi.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Shop, ShopUser

INIT_DATA_MAX_AGE = 24 * 3600


def validate_init_data(init_data: str, bot_token: str, max_age: int = INIT_DATA_MAX_AGE) -> dict | None:
    """To'g'ri bo'lsa Telegram user obyektini qaytaradi."""
    if not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        return json.loads(pairs.get("user", "{}")) or None
    except (ValueError, json.JSONDecodeError):
        return None


@dataclass
class CurrentUser:
    telegram_user_id: int
    shop: Shop
    shop_user: ShopUser


async def current_user(
    authorization: str = Header(default=""),
    x_shop_id: int | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "tma" or not value:
        raise HTTPException(401, "Authorization: tma <initData> kerak")
    user = validate_init_data(value, get_settings().bot_token)
    if user is None or "id" not in user:
        raise HTTPException(401, "initData noto'g'ri yoki eskirgan")
    stmt = (
        select(Shop, ShopUser)
        .join(ShopUser, ShopUser.shop_id == Shop.id)
        .where(ShopUser.telegram_user_id == int(user["id"]))
        .order_by(Shop.id)
    )
    if x_shop_id is not None:
        stmt = stmt.where(Shop.id == x_shop_id)
    row = (await session.execute(stmt.limit(1))).first()
    if row is None:
        raise HTTPException(403, "Do'kon topilmadi. Avval botda /start bosing")
    return CurrentUser(telegram_user_id=int(user["id"]), shop=row.Shop, shop_user=row.ShopUser)


async def owner_only(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.shop_user.role != "owner":
        raise HTTPException(403, "Faqat do'kon egasi uchun")
    return user
