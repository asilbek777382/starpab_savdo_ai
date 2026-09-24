"""Web panel autentifikatsiyasi: telefon + parol, httpOnly cookie ichida JWT sessiya."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.masking import normalize_phone
from app.config import get_settings
from app.models import Account, ShopUser

SESSION_COOKIE = "nv_session"
JWT_ALG = "HS256"
MIN_PASSWORD = 8
LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60
MAGIC_TTL = 10 * 60

_hasher = PasswordHasher()


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Parol kamida {MIN_PASSWORD} ta belgidan iborat bo'lishi kerak")


def parse_phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if not phone:
        raise AuthError("Telefon raqam noto'g'ri. Masalan: +998 90 123 45 67")
    return phone


# ---------- sessiya ----------


def create_session_token(account_id: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(account_id), "iat": now, "exp": now + timedelta(days=s.session_days), "typ": "session"}
    return jwt.encode(payload, s.secret_key, algorithm=JWT_ALG)


def decode_session_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "session":
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


def set_session_cookie(response: Response, account_id: int) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(account_id),
        max_age=s.session_days * 24 * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# ---------- login urinishlari limiti ----------


def _attempts_key(phone: str, ip: str) -> str:
    return f"login:{phone}:{ip}"


async def login_allowed(redis: Redis, phone: str, ip: str) -> bool:
    return int(await redis.get(_attempts_key(phone, ip)) or 0) < LOGIN_ATTEMPTS


async def register_failed_login(redis: Redis, phone: str, ip: str) -> None:
    key = _attempts_key(phone, ip)
    if await redis.incr(key) == 1:
        await redis.expire(key, LOGIN_WINDOW_SECONDS)


async def reset_login_attempts(redis: Redis, phone: str, ip: str) -> None:
    await redis.delete(_attempts_key(phone, ip))


# ---------- bir martalik tokenlar (Telegram ulash, magic link) ----------


async def issue_token(redis: Redis, kind: str, value: str, ttl: int) -> str:
    token = secrets.token_urlsafe(24)
    await redis.set(f"otk:{kind}:{token}", value, ex=ttl)
    return token


async def consume_token(redis: Redis, kind: str, token: str) -> str | None:
    return await redis.getdel(f"otk:{kind}:{token}")


# ---------- akkaunt amallari ----------


async def authenticate(session: AsyncSession, phone: str, password: str) -> Account | None:
    account = await session.scalar(select(Account).where(Account.phone == phone))
    if account is None or not account.is_active or not verify_password(account.password_hash, password):
        return None
    account.last_login_at = datetime.now(UTC)
    return account


async def link_telegram(session: AsyncSession, account: Account, telegram_user_id: int) -> None:
    """Akkauntni Telegram'ga bog'laydi: do'kon xabarnomalari shu Telegram'ga keladi.

    Bot orqali (Telegram'da) yaratilgan do'konlar ham shu akkauntga qo'shiladi.
    """
    other = await session.scalar(
        select(Account).where(Account.telegram_user_id == telegram_user_id, Account.id != account.id)
    )
    if other is not None:
        raise AuthError("Bu Telegram akkaunt boshqa profilga ulangan")
    account.telegram_user_id = telegram_user_id

    rows = list(await session.scalars(select(ShopUser).where(ShopUser.account_id == account.id)))
    tg_rows = list(await session.scalars(select(ShopUser).where(ShopUser.telegram_user_id == telegram_user_id)))
    by_shop = {r.shop_id: r for r in tg_rows}
    for row in rows:
        existing = by_shop.get(row.shop_id)
        if existing is not None and existing.id != row.id:
            existing.account_id = account.id  # bot orqali yaratilgan yozuv qoladi
            await session.delete(row)
        else:
            row.telegram_user_id = telegram_user_id
    for row in tg_rows:
        if row.account_id is None:
            row.account_id = account.id
    await session.flush()


async def account_for_telegram(session: AsyncSession, telegram_user_id: int, name: str) -> Account:
    """Magic link: Telegram foydalanuvchisiga akkaunt topadi yoki yaratadi."""
    account = await session.scalar(select(Account).where(Account.telegram_user_id == telegram_user_id))
    if account is None:
        account = Account(telegram_user_id=telegram_user_id, name=name)
        session.add(account)
        await session.flush()
    rows = await session.scalars(
        select(ShopUser).where(ShopUser.telegram_user_id == telegram_user_id, ShopUser.account_id.is_(None))
    )
    for row in rows:
        row.account_id = account.id
    account.last_login_at = datetime.now(UTC)
    await session.flush()
    return account


def web_url(path: str) -> str:
    s = get_settings()
    base = (s.public_web_url or s.public_base_url).rstrip("/")
    return f"{base}{path}"


async def issue_magic_link(redis: Redis, telegram_user_id: int, name: str) -> str:
    token = await issue_token(redis, "magic", f"{telegram_user_id}:{name}", MAGIC_TTL)
    return web_url(f"/app/magic?token={token}")
