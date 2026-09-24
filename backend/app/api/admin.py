"""Platforma egasi uchun: barcha do'konlar, tariflar, qo'lda to'lovlar."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import platform_admin
from app.db import get_session
from app.models import (
    PLANS,
    Account,
    Channel,
    Lead,
    Order,
    Payment,
    Shop,
    ShopUser,
    Subscription,
    UsageCounter,
)
from app.schemas.api import (
    AdminOverview,
    AdminPaymentIn,
    AdminPlanIn,
    AdminShopDetail,
    AdminShopRow,
    AdminStatusIn,
    ChannelOut,
    PaymentOut,
)
from app.services.billing import activate_subscription
from app.services.usage import period_key

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(platform_admin)])

MONTH_DAYS = 30


async def _paid_until(session: AsyncSession, shop_id: int) -> datetime | None:
    return await session.scalar(
        select(func.max(Subscription.period_end)).where(
            Subscription.shop_id == shop_id, Subscription.status == "active"
        )
    )


async def _row(session: AsyncSession, shop: Shop) -> AdminShopRow:
    since = datetime.now(UTC) - timedelta(days=30)
    owner = (
        await session.execute(
            select(ShopUser.name, Account.name, Account.phone)
            .outerjoin(Account, Account.id == ShopUser.account_id)
            .where(ShopUser.shop_id == shop.id, ShopUser.role == "owner")
            .order_by(ShopUser.id)
            .limit(1)
        )
    ).first()
    usage = await session.get(UsageCounter, (shop.id, period_key()))
    orders = await session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.shop_id == shop.id, Order.created_at >= since, Order.source == "ai")
    )
    leads = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.shop_id == shop.id, Lead.created_at >= since, Lead.channel_type != "test")
    )
    business = await session.scalar(
        select(Channel.id).where(Channel.shop_id == shop.id, Channel.type == "tg_business", Channel.is_enabled)
    )
    instagram = await session.scalar(
        select(Channel.id).where(Channel.shop_id == shop.id, Channel.type == "instagram", Channel.is_enabled)
    )
    return AdminShopRow(
        id=shop.id,
        name=shop.name,
        owner_name=(owner[1] or owner[0]) if owner else None,
        owner_phone=owner[2] if owner else None,
        plan=shop.plan,
        status=shop.status,
        trial_ends_at=shop.trial_ends_at,
        paid_until=await _paid_until(session, shop.id),
        month_conversations=usage.conversations if usage else 0,
        month_cost=usage.cost if usage else 0,
        orders_30d=int(orders or 0),
        leads_30d=int(leads or 0),
        business_connected=business is not None,
        instagram_connected=instagram is not None,
        created_at=shop.created_at,
    )


async def _get_shop(session: AsyncSession, shop_id: int) -> Shop:
    shop = await session.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(404)
    return shop


@router.get("/overview", response_model=AdminOverview)
async def overview(session: AsyncSession = Depends(get_session)) -> AdminOverview:
    now = datetime.now(UTC)
    shops = await session.scalar(select(func.count()).select_from(Shop))
    trials = await session.scalar(
        select(func.count()).select_from(Shop).where(Shop.plan == "trial", Shop.trial_ends_at > now)
    )
    paying_rows = (
        await session.execute(
            select(Shop.plan)
            .join(Subscription, Subscription.shop_id == Shop.id)
            .where(Subscription.status == "active", Subscription.period_end > now)
            .distinct(Shop.id)
        )
    ).all()
    usage = (
        await session.execute(
            select(
                func.coalesce(func.sum(UsageCounter.conversations), 0), func.coalesce(func.sum(UsageCounter.cost), 0)
            ).where(UsageCounter.period == period_key())
        )
    ).one()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == "paid", Payment.created_at >= month_start
        )
    )
    return AdminOverview(
        shops=int(shops or 0),
        trials_active=int(trials or 0),
        paying=len(paying_rows),
        mrr=sum(PLANS.get(r.plan, PLANS["start"])["price"] for r in paying_rows),
        month_conversations=int(usage[0]),
        month_ai_cost=usage[1],
        month_revenue=int(revenue or 0),
    )


@router.get("/shops", response_model=list[AdminShopRow])
async def list_shops(
    q: str | None = None, limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_session)
):
    stmt = select(Shop).order_by(Shop.id.desc()).limit(min(limit, 200)).offset(offset)
    if q:
        stmt = stmt.where(Shop.name.ilike(f"%{q}%"))
    return [await _row(session, shop) for shop in await session.scalars(stmt)]


@router.get("/shops/{shop_id}", response_model=AdminShopDetail)
async def shop_detail(shop_id: int, session: AsyncSession = Depends(get_session)):
    shop = await _get_shop(session, shop_id)
    payments = await session.scalars(
        select(Payment).where(Payment.shop_id == shop_id).order_by(Payment.id.desc()).limit(50)
    )
    channels = await session.scalars(select(Channel).where(Channel.shop_id == shop_id))
    return AdminShopDetail(
        shop=await _row(session, shop),
        payments=[PaymentOut.model_validate(p) for p in payments],
        channels=[ChannelOut.model_validate(c) for c in channels],
    )


@router.post("/shops/{shop_id}/plan", response_model=AdminShopRow)
async def change_plan(shop_id: int, body: AdminPlanIn, session: AsyncSession = Depends(get_session)):
    shop = await _get_shop(session, shop_id)
    if body.plan is not None:
        shop.plan = body.plan
    if body.trial_days is not None:
        base = max(shop.trial_ends_at or datetime.now(UTC), datetime.now(UTC))
        shop.trial_ends_at = base + timedelta(days=body.trial_days)
    if body.extra_conversations is not None:
        shop.extra_conversations = body.extra_conversations
    await session.commit()
    return await _row(session, shop)


@router.post("/shops/{shop_id}/status", response_model=AdminShopRow)
async def change_status(shop_id: int, body: AdminStatusIn, session: AsyncSession = Depends(get_session)):
    shop = await _get_shop(session, shop_id)
    shop.status = body.status
    await session.commit()
    return await _row(session, shop)


@router.post("/shops/{shop_id}/payments", response_model=AdminShopDetail, status_code=201)
async def add_payment(shop_id: int, body: AdminPaymentIn, session: AsyncSession = Depends(get_session)):
    """Qo'lda to'lov (karta o'tkazmasi va chek): obuna davri uzaytiriladi va tarif o'rnatiladi."""
    shop = await _get_shop(session, shop_id)
    session.add(
        Payment(
            shop_id=shop_id,
            amount=body.amount,
            provider=body.provider,
            provider_txn_id=body.note,
            status="paid",
            plan=body.plan,
            months=body.months,
        )
    )
    await activate_subscription(session, shop, body.plan, body.months)
    await session.commit()
    return await shop_detail(shop_id, session)
