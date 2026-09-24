from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, owner_only
from app.db import get_session
from app.models import ShopSettings
from app.schemas.api import MeOut, SettingsIO, ShopOut, ShopUpdate
from app.telegram.handlers import bot_link

router = APIRouter(prefix="/api", tags=["shop"])


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser = Depends(current_user)) -> MeOut:
    return MeOut(
        telegram_user_id=user.telegram_user_id,
        role=user.shop_user.role,
        shop=ShopOut.model_validate(user.shop),
        bot_link=bot_link(user.shop.id),
    )


@router.put("/shop", response_model=ShopOut)
async def update_shop(
    body: ShopUpdate, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
) -> ShopOut:
    shop = user.shop
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(shop, field, value)
    await session.commit()
    return ShopOut.model_validate(shop)


@router.get("/settings", response_model=SettingsIO)
async def get_shop_settings(
    user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> SettingsIO:
    return SettingsIO.model_validate(await session.get(ShopSettings, user.shop.id))


@router.put("/settings", response_model=SettingsIO)
async def put_shop_settings(
    body: SettingsIO, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
) -> SettingsIO:
    settings = await session.get(ShopSettings, user.shop.id)
    for field, value in body.model_dump(mode="json").items():
        setattr(settings, field, value)
    await session.commit()
    return SettingsIO.model_validate(settings)
