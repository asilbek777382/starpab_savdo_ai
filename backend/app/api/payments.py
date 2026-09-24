"""Obuna to'lovi: sotuvchi panelidan checkout, Payme/Click callback'lari."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, owner_only
from app.db import get_session
from app.models import PLANS, YEARLY_DISCOUNT, Payment
from app.payments import click, payme
from app.schemas.api import BillingOut, CheckoutIn, CheckoutOut, PaymentOut, PlanInfo
from app.services import billing
from app.services.auth import web_url
from app.services.usage import current_usage

router = APIRouter(tags=["billing"])


@router.get("/api/billing", response_model=BillingOut)
async def billing_info(user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    shop = user.shop
    usage = await current_usage(session, shop.id)
    payments = await session.scalars(
        select(Payment)
        .where(Payment.shop_id == shop.id, Payment.status != "pending")
        .order_by(Payment.id.desc())
        .limit(50)
    )
    providers = [
        name for name, ok in (("payme", billing.payme_configured()), ("click", billing.click_configured())) if ok
    ]
    return BillingOut(
        plan=shop.plan,
        status=shop.status,
        trial_ends_at=shop.trial_ends_at,
        paid_until=await billing.paid_until(session, shop.id),
        month_conversations=usage.conversations if usage else 0,
        month_limit=PLANS.get(shop.plan, PLANS["start"])["conversations"] + (shop.extra_conversations or 0),
        plans=[
            PlanInfo(
                code=code,
                price=p["price"],
                conversations=p["conversations"],
                max_products=p["max_products"],
                instagram=p["instagram"],
            )
            for code, p in PLANS.items()
            if code in billing.PAYABLE_PLANS
        ],
        providers=providers,
        yearly_discount=YEARLY_DISCOUNT,
        payments=[PaymentOut.model_validate(p) for p in payments],
    )


@router.post("/api/billing/checkout", response_model=CheckoutOut)
async def checkout(
    body: CheckoutIn, user: CurrentUser = Depends(owner_only), session: AsyncSession = Depends(get_session)
):
    configured = billing.payme_configured() if body.provider == "payme" else billing.click_configured()
    if not configured:
        raise HTTPException(503, "Bu to'lov usuli hali ulanmagan")
    payment = await billing.create_invoice(session, user.shop, body.plan, body.months, body.provider)
    await session.commit()
    back = web_url("/app/billing?paid=1")
    url = (
        billing.payme_checkout_url(payment, back)
        if body.provider == "payme"
        else billing.click_checkout_url(payment, back)
    )
    return CheckoutOut(url=url, payment_id=payment.id, amount=payment.amount)


@router.post("/api/payments/payme", include_in_schema=False)
async def payme_endpoint(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return payme.error_body(payme.ERR_PARSE, None)
    if not payme.authorized(request.headers.get("authorization", "")):
        return payme.error_body(payme.ERR_AUTH, body.get("id") if isinstance(body, dict) else None)
    if not isinstance(body, dict):
        return payme.error_body(payme.ERR_PARSE, None)
    return await payme.handle(session, body)


async def _form(request: Request) -> dict:
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


@router.post("/api/payments/click/prepare", include_in_schema=False)
async def click_prepare(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    return await click.prepare(session, await _form(request))


@router.post("/api/payments/click/complete", include_in_schema=False)
async def click_complete(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    return await click.complete(session, await _form(request))
