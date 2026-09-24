"""Xodimlar va rollar (faqat do'kon egasi boshqaradi)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, owner_only
from app.db import get_session
from app.models import Account, ShopUser
from app.runtime import get_runtime
from app.schemas.api import StaffIn, StaffOut, StaffUpdate
from app.services import auth as auth_svc
from app.services import staff as staff_svc

router = APIRouter(prefix="/api/staff", tags=["staff"])


def _out(member: ShopUser, account: Account | None, me: ShopUser, invite_url: str | None = None) -> StaffOut:
    return StaffOut(
        id=member.id,
        name=(account.name if account else None) or member.name or "—",
        phone=account.phone if account else None,
        role=member.role,
        notify=member.notify,
        telegram_linked=member.telegram_user_id is not None,
        pending=staff_svc.needs_invite(account) and account.telegram_user_id is None,
        is_me=member.id == me.id,
        invite_url=invite_url,
    )


async def _member(session: AsyncSession, user: CurrentUser, member_id: int) -> tuple[ShopUser, Account | None]:
    member = await session.get(ShopUser, member_id)
    if member is None or member.shop_id != user.shop.id:
        raise HTTPException(404, "Xodim topilmadi")
    account = await session.get(Account, member.account_id) if member.account_id else None
    return member, account


@router.get("", response_model=list[StaffOut])
async def list_staff(user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(ShopUser, Account)
        .outerjoin(Account, Account.id == ShopUser.account_id)
        .where(ShopUser.shop_id == user.shop.id)
        .order_by(ShopUser.id)
    )
    return [_out(m, a, user.shop_user) for m, a in rows]


@router.post("", response_model=StaffOut, status_code=201)
async def add_staff(
    body: StaffIn, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
):
    try:
        phone = auth_svc.parse_phone(body.phone)
        member, account = await staff_svc.add_member(session, user.shop, phone, body.name.strip(), body.role)
    except auth_svc.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    except staff_svc.StaffError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    await session.commit()
    invite = await staff_svc.issue_invite(get_runtime().redis, account) if staff_svc.needs_invite(account) else None
    return _out(member, account, user.shop_user, invite)


@router.patch("/{member_id}", response_model=StaffOut)
async def update_staff(
    member_id: int,
    body: StaffUpdate,
    user: CurrentUser = Depends(owner_only),
    session: AsyncSession = Depends(get_session),
):
    member, account = await _member(session, user, member_id)
    if body.notify is not None:
        member.notify = body.notify
    if body.role is not None:
        try:
            await staff_svc.change_role(session, member, body.role)
        except staff_svc.StaffError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
    await session.commit()
    return _out(member, account, user.shop_user)


@router.post("/{member_id}/invite", response_model=StaffOut)
async def reissue_invite(
    member_id: int, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
):
    member, account = await _member(session, user, member_id)
    if not staff_svc.needs_invite(account):
        raise HTTPException(409, "Xodim allaqachon parol o'rnatgan — u telefon va paroli bilan kiradi")
    return _out(member, account, user.shop_user, await staff_svc.issue_invite(get_runtime().redis, account))


@router.delete("/{member_id}", status_code=204)
async def remove_staff(
    member_id: int, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
) -> None:
    member, _ = await _member(session, user, member_id)
    try:
        await staff_svc.remove_member(session, member, user.shop_user)
    except staff_svc.StaffError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    await session.commit()
