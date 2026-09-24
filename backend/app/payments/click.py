"""Click SHOP API: Prepare (action=0) va Complete (action=1). Click bizning endpointlarimizni chaqiradi.

Imzo: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id [+ merchant_prepare_id] + amount + action
+ sign_time). merchant_trans_id — bizning Payment.id; summa so'mda.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Payment, Shop
from app.services.billing import activate_subscription

OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TXN_NOT_FOUND = -6
ERR_BAD_REQUEST = -8
ERR_CANCELLED = -9

NOTES = {
    OK: "Success",
    ERR_SIGN: "SIGN CHECK FAILED!",
    ERR_AMOUNT: "Incorrect parameter amount",
    ERR_ACTION: "Action not found",
    ERR_ALREADY_PAID: "Already paid",
    ERR_ORDER_NOT_FOUND: "Order does not exist",
    ERR_TXN_NOT_FOUND: "Transaction does not exist",
    ERR_BAD_REQUEST: "Error in request from click",
    ERR_CANCELLED: "Transaction cancelled",
}


def sign(p: dict, with_prepare_id: bool) -> str:
    parts = [p.get("click_trans_id", ""), p.get("service_id", ""), get_settings().click_secret_key]
    parts.append(p.get("merchant_trans_id", ""))
    if with_prepare_id:
        parts.append(p.get("merchant_prepare_id", ""))
    parts += [p.get("amount", ""), p.get("action", ""), p.get("sign_time", "")]
    return hashlib.md5("".join(str(x) for x in parts).encode()).hexdigest()  # noqa: S324 — Click talabi


def _reply(p: dict, error: int, **extra) -> dict:
    return {
        "click_trans_id": p.get("click_trans_id"),
        "merchant_trans_id": p.get("merchant_trans_id"),
        "error": error,
        "error_note": NOTES[error],
        **extra,
    }


async def _validate(session: AsyncSession, p: dict, action: int) -> tuple[int, Payment | None]:
    required = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string")
    if any(k not in p for k in required) or not get_settings().click_secret_key:
        return ERR_BAD_REQUEST, None
    if not hmac.compare_digest(sign(p, with_prepare_id=action == 1), str(p["sign_string"])):
        return ERR_SIGN, None
    if str(p["action"]) != str(action):
        return ERR_ACTION, None
    if str(p["service_id"]) != get_settings().click_service_id:
        return ERR_BAD_REQUEST, None
    mtid = str(p["merchant_trans_id"])
    payment = await session.get(Payment, int(mtid), with_for_update=True) if mtid.isdigit() else None
    if payment is None or payment.provider != "click":
        return ERR_ORDER_NOT_FOUND, None
    if payment.status == "paid":
        return ERR_ALREADY_PAID, payment
    if payment.status == "cancelled":
        return ERR_CANCELLED, payment
    try:
        amount = Decimal(str(p["amount"]))
    except InvalidOperation:
        return ERR_AMOUNT, payment
    if amount != Decimal(payment.amount):
        return ERR_AMOUNT, payment
    return OK, payment


async def prepare(session: AsyncSession, p: dict) -> dict:
    error, payment = await _validate(session, p, action=0)
    if error != OK:
        return _reply(p, error)
    payment.provider_txn_id = str(p["click_trans_id"])
    payment.state = 1
    await session.commit()
    return _reply(p, OK, merchant_prepare_id=payment.id)


async def complete(session: AsyncSession, p: dict) -> dict:
    error, payment = await _validate(session, p, action=1)
    if error == ERR_ALREADY_PAID and payment is not None:
        return _reply(p, ERR_ALREADY_PAID, merchant_confirm_id=payment.id)
    if error != OK:
        return _reply(p, error)
    if str(p.get("merchant_prepare_id")) != str(payment.id) or payment.provider_txn_id != str(p["click_trans_id"]):
        return _reply(p, ERR_TXN_NOT_FOUND)
    if int(p.get("error", 0) or 0) < 0:
        # Click tomonida pul yechilmadi — buyurtma bekor
        payment.status, payment.state = "cancelled", -1
        payment.cancel_time = datetime.now(UTC)
        await session.commit()
        return _reply(p, ERR_CANCELLED)
    payment.status, payment.state = "paid", 2
    payment.perform_time = datetime.now(UTC)
    shop = await session.get(Shop, payment.shop_id)
    await activate_subscription(session, shop, payment.plan or "start", payment.months or 1)
    await session.commit()
    return _reply(p, OK, merchant_confirm_id=payment.id)
