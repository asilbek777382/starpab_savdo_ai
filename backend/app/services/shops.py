from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Channel, Shop, ShopSettings, ShopUser


async def create_shop(session: AsyncSession, owner_tg_id: int, owner_name: str | None, name: str) -> Shop:
    shop = Shop(name=name, plan="trial", trial_ends_at=datetime.now(UTC) + timedelta(days=get_settings().trial_days))
    session.add(shop)
    await session.flush()
    session.add(ShopSettings(shop_id=shop.id, delivery_zones=[], handoff_rules={}))
    session.add(ShopUser(shop_id=shop.id, telegram_user_id=owner_tg_id, name=owner_name, role="owner"))
    await session.flush()
    return shop


async def shops_of_user(session: AsyncSession, tg_user_id: int) -> list[tuple[Shop, ShopUser]]:
    rows = await session.execute(
        select(Shop, ShopUser)
        .join(ShopUser, ShopUser.shop_id == Shop.id)
        .where(ShopUser.telegram_user_id == tg_user_id)
        .order_by(Shop.id)
    )
    return [(r.Shop, r.ShopUser) for r in rows]


async def get_channel(session: AsyncSession, shop_id: int, type_: str) -> Channel:
    """Do'kon uchun tg_bot / test kanalini oladi yoki yaratadi."""
    channel = await session.scalar(select(Channel).where(Channel.shop_id == shop_id, Channel.type == type_))
    if channel is None:
        channel = Channel(shop_id=shop_id, type=type_, can_reply=True, is_enabled=True)
        session.add(channel)
        await session.flush()
    return channel
