from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user
from app.db import get_session
from app.models import ORDER_STATUSES, Order
from app.schemas.api import OrderOut, OrderStatusIn
from app.services.orders import get_order, set_order_status
from app.telegram.handlers import notify_customer_about_order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Order).where(Order.shop_id == user.shop.id).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    rows = await session.scalars(stmt.limit(min(limit, 200)).offset(offset))
    return [OrderOut.model_validate(o) for o in rows]


@router.get("/{order_id}", response_model=OrderOut)
async def order_detail(
    order_id: int, user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    order = await get_order(session, user.shop.id, order_id)
    if order is None:
        raise HTTPException(404)
    return OrderOut.model_validate(order)


@router.post("/{order_id}/status", response_model=OrderOut)
async def change_status(
    order_id: int,
    body: OrderStatusIn,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in ORDER_STATUSES:
        raise HTTPException(422, f"Holat quyidagilardan biri bo'lishi kerak: {', '.join(ORDER_STATUSES)}")
    order = await get_order(session, user.shop.id, order_id)
    if order is None:
        raise HTTPException(404)
    changed = order.status != body.status
    await set_order_status(session, order, body.status)
    await session.commit()
    if changed:
        await notify_customer_about_order(session, order)
    return OrderOut.model_validate(order)
