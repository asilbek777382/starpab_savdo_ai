"""Obuna: narx, hisob-faktura (Payment), faollashtirish va to'lov havolalari."""

import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PLANS, YEARLY_DISCOUNT, Payment, Shop, Subscription

MONTH_DAYS = 30
PAYABLE_PLANS = ("start", "business", "pro")


class BillingError(Exception):
    pass


def plan_price(plan: str, months: int) -> int:
    if plan not in PAYABLE_PLANS:
        raise BillingError("Noma'lum tarif")
    if months not in (1, 3, 6, 12):
        raise BillingError("Muddat 1, 3, 6 yoki 12 oy bo'lishi mumkin")
    total = PLANS[plan]["price"] * months
    if months == 12:
        total = round(total * (1 - YEARLY_DISCOUNT))
    return int(total)


async def paid_until(session: AsyncSession, shop_id: int) -> datetime | None:
    return await session.scalar(
        select(func.max(Subscription.period_end)).where(
            Subscription.shop_id == shop_id, Subscription.status == "active"
        )
    )


async def activate_subscription(session: AsyncSession, shop: Shop, plan: str, months: int) -> Subscription:
    """Obunani uzaytiradi: yangi davr joriy to'langan muddat tugagan joydan (yoki hozirdan) boshlanadi."""
    now = datetime.now(UTC)
    start = max(await paid_until(session, shop.id) or now, now)
    sub = Subscription(
        shop_id=shop.id,
        plan=plan,
        period_start=start,
        period_end=start + timedelta(days=MONTH_DAYS * months),
        status="active",
    )
    session.add(sub)
    shop.plan = plan
    shop.status = "active"
    await session.flush()
    return sub


async def create_invoice(session: AsyncSession, shop: Shop, plan: str, months: int, provider: str) -> Payment:
    payment = Payment(
        shop_id=shop.id, amount=plan_price(plan, months), provider=provider, plan=plan, months=months, status="pending"
    )
    session.add(payment)
    await session.flush()
    return payment


def payme_configured() -> bool:
    s = get_settings()
    return bool(s.payme_merchant_id and s.payme_key)


def click_configured() -> bool:
    s = get_settings()
    return bool(s.click_service_id and s.click_merchant_id and s.click_secret_key)


def payme_checkout_url(payment: Payment, return_url: str) -> str:
    """checkout.paycom.uz/<base64("m=...;ac.order_id=...;a=<tiyin>;c=<qaytish>")>"""
    s = get_settings()
    params = f"m={s.payme_merchant_id};ac.order_id={payment.id};a={payment.amount * 100};c={return_url}"
    return f"{s.payme_checkout_url}/{base64.b64encode(params.encode()).decode()}"


def click_checkout_url(payment: Payment, return_url: str) -> str:
    s = get_settings()
    query = {
        "service_id": s.click_service_id,
        "merchant_id": s.click_merchant_id,
        "amount": payment.amount,
        "transaction_param": payment.id,
        "return_url": return_url,
    }
    return f"{s.click_pay_url}?{urlencode(query)}"
