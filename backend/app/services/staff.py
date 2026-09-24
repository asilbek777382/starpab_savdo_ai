"""Do'kon xodimlari: egasi operatorlarni telefon raqami bilan taklif qiladi.

Rollar: owner — hamma narsa (sozlamalar, ulash, to'lov, xodimlar); operator — buyurtmalar, lidlar, suhbatlar,
katalog va test chat. Yangi xodim uchun parolsiz akkaunt yaratiladi va bir martalik taklif havolasi beriladi —
xodim havolani ochib o'z parolini o'rnatadi.
"""

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Shop, ShopUser
from app.services.auth import consume_token, issue_token, web_url

ROLES = ("owner", "operator")
INVITE_TTL = 7 * 24 * 3600


class StaffError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


async def add_member(session: AsyncSession, shop: Shop, phone: str, name: str, role: str) -> tuple[ShopUser, Account]:
    account = await session.scalar(select(Account).where(Account.phone == phone))
    if account is None:
        account = Account(phone=phone, name=name)
        session.add(account)
        await session.flush()
    elif await session.scalar(
        select(ShopUser.id).where(ShopUser.shop_id == shop.id, ShopUser.account_id == account.id)
    ):
        raise StaffError("Bu raqam allaqachon do'kon xodimi", 409)
    member = ShopUser(
        shop_id=shop.id, account_id=account.id, telegram_user_id=account.telegram_user_id, name=name, role=role
    )
    session.add(member)
    await session.flush()
    return member, account


async def _owners(session: AsyncSession, shop_id: int) -> int:
    return await session.scalar(
        select(func.count()).select_from(ShopUser).where(ShopUser.shop_id == shop_id, ShopUser.role == "owner")
    )


async def change_role(session: AsyncSession, member: ShopUser, role: str) -> None:
    if member.role == "owner" and role != "owner" and await _owners(session, member.shop_id) <= 1:
        raise StaffError("Do'konda kamida bitta egasi qolishi kerak")
    member.role = role


async def remove_member(session: AsyncSession, member: ShopUser, actor: ShopUser) -> None:
    if member.id == actor.id:
        raise StaffError("O'zingizni o'chira olmaysiz")
    if member.role == "owner" and await _owners(session, member.shop_id) <= 1:
        raise StaffError("Do'konda kamida bitta egasi qolishi kerak")
    await session.delete(member)


def needs_invite(account: Account | None) -> bool:
    """Parol o'rnatmagan va Telegram orqali ham kira olmaydigan akkauntga taklif havolasi kerak."""
    return account is not None and not account.password_hash


async def issue_invite(redis: Redis, account: Account) -> str:
    token = await issue_token(redis, "invite", str(account.id), INVITE_TTL)
    return web_url(f"/app/invite?token={token}")


async def peek_invite(redis: Redis, token: str) -> int | None:
    value = await redis.get(f"otk:invite:{token}")
    return int(value) if value and value.isdigit() else None


async def accept_invite(redis: Redis, token: str) -> int | None:
    value = await consume_token(redis, "invite", token)
    return int(value) if value and value.isdigit() else None
