from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_account
from app.config import get_settings
from app.db import get_session
from app.models import Account, Shop, ShopUser
from app.runtime import get_runtime
from app.schemas.api import (
    AccountOut,
    InviteAcceptIn,
    InviteInfo,
    LinkOut,
    LoginIn,
    MagicIn,
    PasswordIn,
    ProfileIn,
    RegisterIn,
    ShopBrief,
)
from app.services import auth as auth_svc
from app.services import staff as staff_svc
from app.services.shops import create_shop

router = APIRouter(prefix="/api/auth", tags=["auth"])

TG_LINK_TTL = 15 * 60


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


async def account_out(session: AsyncSession, account: Account) -> AccountOut:
    rows = await session.execute(
        select(Shop, ShopUser.role)
        .join(ShopUser, ShopUser.shop_id == Shop.id)
        .where(ShopUser.account_id == account.id)
        .order_by(Shop.id)
    )
    return AccountOut(
        id=account.id,
        name=account.name,
        phone=account.phone,
        lang=account.lang,
        telegram_linked=account.telegram_user_id is not None,
        has_password=bool(account.password_hash),
        is_platform_admin=account.is_platform_admin,
        shops=[ShopBrief(id=s.id, name=s.name, role=role, plan=s.plan, status=s.status) for s, role in rows],
    )


def _bad_request(exc: auth_svc.AuthError) -> HTTPException:
    return HTTPException(422, str(exc))


@router.post("/register", response_model=AccountOut, status_code=201)
async def register(body: RegisterIn, response: Response, session: AsyncSession = Depends(get_session)):
    try:
        phone = auth_svc.parse_phone(body.phone)
        auth_svc.validate_password(body.password)
    except auth_svc.AuthError as exc:
        raise _bad_request(exc) from exc
    if await session.scalar(select(Account.id).where(Account.phone == phone)):
        raise HTTPException(409, "Bu telefon raqam bilan akkaunt allaqachon bor. Kirish sahifasidan foydalaning")
    account = Account(
        phone=phone, password_hash=auth_svc.hash_password(body.password), name=body.name.strip(), lang=body.lang
    )
    session.add(account)
    await session.flush()
    await create_shop(session, None, account.name, body.shop_name.strip(), account_id=account.id)
    await session.commit()
    auth_svc.set_session_cookie(response, account.id)
    return await account_out(session, account)


@router.post("/login", response_model=AccountOut)
async def login(body: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    redis = get_runtime().redis
    try:
        phone = auth_svc.parse_phone(body.phone)
    except auth_svc.AuthError as exc:
        raise _bad_request(exc) from exc
    ip = _client_ip(request)
    if not await auth_svc.login_allowed(redis, phone, ip):
        raise HTTPException(429, "Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring")
    account = await auth_svc.authenticate(session, phone, body.password)
    if account is None:
        await auth_svc.register_failed_login(redis, phone, ip)
        raise HTTPException(401, "Telefon yoki parol noto'g'ri")
    await auth_svc.reset_login_attempts(redis, phone, ip)
    await session.commit()
    auth_svc.set_session_cookie(response, account.id)
    return await account_out(session, account)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    auth_svc.clear_session_cookie(response)


@router.get("/me", response_model=AccountOut)
async def me(account: Account = Depends(current_account), session: AsyncSession = Depends(get_session)):
    return await account_out(session, account)


@router.patch("/me", response_model=AccountOut)
async def update_profile(
    body: ProfileIn, account: Account = Depends(current_account), session: AsyncSession = Depends(get_session)
):
    if body.name is not None:
        account.name = body.name.strip()
    if body.lang is not None:
        account.lang = body.lang
    await session.commit()
    return await account_out(session, account)


@router.post("/password", response_model=AccountOut)
async def change_password(
    body: PasswordIn, account: Account = Depends(current_account), session: AsyncSession = Depends(get_session)
):
    if account.password_hash and not auth_svc.verify_password(account.password_hash, body.old_password or ""):
        raise HTTPException(403, "Joriy parol noto'g'ri")
    try:
        auth_svc.validate_password(body.new_password)
        if account.phone is None:
            if not body.phone:
                raise auth_svc.AuthError("Kirish uchun telefon raqamingizni kiriting")
            phone = auth_svc.parse_phone(body.phone)
            if await session.scalar(select(Account.id).where(Account.phone == phone, Account.id != account.id)):
                raise auth_svc.AuthError("Bu telefon raqam boshqa akkauntda ishlatilgan")
            account.phone = phone
    except auth_svc.AuthError as exc:
        raise _bad_request(exc) from exc
    account.password_hash = auth_svc.hash_password(body.new_password)
    await session.commit()
    return await account_out(session, account)


@router.post("/telegram-link", response_model=LinkOut)
async def telegram_link(account: Account = Depends(current_account)) -> LinkOut:
    token = await auth_svc.issue_token(get_runtime().redis, "tglink", str(account.id), TG_LINK_TTL)
    return LinkOut(url=f"https://t.me/{get_settings().bot_username}?start=link_{token}", expires_in=TG_LINK_TTL)


@router.post("/magic", response_model=AccountOut)
async def magic_login(body: MagicIn, response: Response, session: AsyncSession = Depends(get_session)):
    """Telegram botdagi /web buyrug'i bergan bir martalik havola orqali kirish."""
    value = await auth_svc.consume_token(get_runtime().redis, "magic", body.token)
    if value is None:
        raise HTTPException(401, "Havola eskirgan yoki ishlatilgan. Botda /web buyrug'ini qayta yuboring")
    tg_id, _, name = value.partition(":")
    account = await auth_svc.account_for_telegram(session, int(tg_id), name)
    await session.commit()
    auth_svc.set_session_cookie(response, account.id)
    return await account_out(session, account)


INVITE_EXPIRED = "Taklif havolasi eskirgan yoki ishlatilgan. Do'kon egasidan yangi havola so'rang"


async def _invited_account(session: AsyncSession, token: str) -> Account:
    account_id = await staff_svc.peek_invite(get_runtime().redis, token)
    account = await session.get(Account, account_id) if account_id else None
    if account is None or not account.is_active or not staff_svc.needs_invite(account):
        raise HTTPException(401, INVITE_EXPIRED)
    return account


@router.get("/invite", response_model=InviteInfo)
async def invite_info(token: str, session: AsyncSession = Depends(get_session)):
    """Xodim taklif havolasini ochdi: kim va qaysi do'konga taklif qilinganini ko'rsatadi."""
    account = await _invited_account(session, token)
    shops = await session.scalars(
        select(Shop.name).join(ShopUser, ShopUser.shop_id == Shop.id).where(ShopUser.account_id == account.id)
    )
    return InviteInfo(name=account.name, phone=account.phone, shops=list(shops))


@router.post("/invite", response_model=AccountOut)
async def accept_invite(body: InviteAcceptIn, response: Response, session: AsyncSession = Depends(get_session)):
    """Xodim parolini o'rnatadi va panelga kiradi. Havola bir martalik."""
    account = await _invited_account(session, body.token)
    try:
        auth_svc.validate_password(body.password)
    except auth_svc.AuthError as exc:
        raise _bad_request(exc) from exc
    if await staff_svc.accept_invite(get_runtime().redis, body.token) != account.id:
        raise HTTPException(401, INVITE_EXPIRED)
    account.password_hash = auth_svc.hash_password(body.password)
    await session.commit()
    auth_svc.set_session_cookie(response, account.id)
    return await account_out(session, account)
