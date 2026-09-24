"""Panel autentifikatsiyasi.

1. Web: httpOnly cookie ichidagi sessiya (telefon + parol bilan kirilgan).
2. Telegram Mini App: Authorization: tma <initData> (HMAC bilan tekshiriladi).
Bir nechta do'koni bo'lsa X-Shop-Id bilan tanlanadi.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Account, Shop, ShopUser
from app.services.auth import SESSION_COOKIE, decode_session_token

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
    telegram_user_id: int | None
    shop: Shop
    shop_user: ShopUser
    account: Account | None = None

    @property
    def test_customer_id(self) -> int:
        """Test chatdagi "mijoz" identifikatori (Telegram ulanmagan bo'lsa manfiy akkaunt id)."""
        if self.telegram_user_id:
            return self.telegram_user_id
        return -(self.account.id if self.account else self.shop_user.id)


async def session_account(request: Request, session: AsyncSession = Depends(get_session)) -> Account | None:
    token = request.cookies.get(SESSION_COOKIE)
    account_id = decode_session_token(token) if token else None
    if account_id is None:
        return None
    account = await session.get(Account, account_id)
    return account if account is not None and account.is_active else None


async def current_account(account: Account | None = Depends(session_account)) -> Account:
    if account is None:
        raise HTTPException(401, "Tizimga kiring")
    return account


async def platform_admin(account: Account = Depends(current_account)) -> Account:
    if not account.is_platform_admin:
        raise HTTPException(403, "Faqat platforma admini uchun")
    return account


async def current_user(
    authorization: str = Header(default=""),
    x_shop_id: int | None = Header(default=None),
    account: Account | None = Depends(session_account),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    stmt = select(Shop, ShopUser).join(ShopUser, ShopUser.shop_id == Shop.id).order_by(Shop.id)
    telegram_user_id: int | None
    if account is not None:
        stmt = stmt.where(ShopUser.account_id == account.id)
        telegram_user_id = account.telegram_user_id
    else:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "tma" or not value:
            raise HTTPException(401, "Tizimga kiring")
        user = validate_init_data(value, get_settings().bot_token)
        if user is None or "id" not in user:
            raise HTTPException(401, "initData noto'g'ri yoki eskirgan")
        telegram_user_id = int(user["id"])
        stmt = stmt.where(ShopUser.telegram_user_id == telegram_user_id)
    if x_shop_id is not None:
        stmt = stmt.where(Shop.id == x_shop_id)
    row = (await session.execute(stmt.limit(1))).first()
    if row is None:
        raise HTTPException(403, "Do'kon topilmadi")
    return CurrentUser(telegram_user_id=telegram_user_id, shop=row.Shop, shop_user=row.ShopUser, account=account)


async def owner_only(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.shop_user.role != "owner":
        raise HTTPException(403, "Faqat do'kon egasi uchun")
    return user
