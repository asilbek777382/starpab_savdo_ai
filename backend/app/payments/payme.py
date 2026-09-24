"""Payme Merchant API (JSON-RPC). Payme bizning endpointimizni chaqiradi; javob har doim HTTP 200.

Holatlar: 1 — yaratilgan, 2 — bajarilgan, -1 — bajarilishdan oldin bekor, -2 — bajarilgandan keyin bekor.
Summalar tiyinda (so'm * 100), vaqtlar millisekundda.
"""

import base64
import hmac
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Payment, Shop
from app.services.billing import activate_subscription

# Yaratilgan, lekin bajarilmagan tranzaksiya shu vaqtdan keyin eskiradi (Payme: 12 soat)
TRANSACTION_TIMEOUT_MS = 12 * 3600 * 1000
REASON_TIMEOUT = 4

ERR_AUTH = -32504
ERR_METHOD = -32601
ERR_PARSE = -32700
ERR_AMOUNT = -31001
ERR_NOT_FOUND = -31003
ERR_CANNOT_CANCEL = -31007
ERR_CANNOT_PERFORM = -31008
ERR_ORDER_NOT_FOUND = -31050
ERR_ORDER_BUSY = -31051

MESSAGES = {
    ERR_AUTH: ("Недостаточно привилегий", "Ruxsat yo'q", "Insufficient privileges"),
    ERR_METHOD: ("Метод не найден", "Metod topilmadi", "Method not found"),
    ERR_PARSE: ("Ошибка разбора JSON", "JSON xatosi", "Parse error"),
    ERR_AMOUNT: ("Неверная сумма", "Summa noto'g'ri", "Invalid amount"),
    ERR_NOT_FOUND: ("Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"),
    ERR_CANNOT_CANCEL: ("Услуга уже оказана", "Xizmat allaqachon ko'rsatilgan", "Service already provided"),
    ERR_CANNOT_PERFORM: ("Невозможно выполнить операцию", "Amalni bajarib bo'lmaydi", "Unable to perform"),
    ERR_ORDER_NOT_FOUND: ("Заказ не найден", "Buyurtma topilmadi", "Order not found"),
    ERR_ORDER_BUSY: ("Заказ уже оплачивается или оплачен", "Buyurtma to'lanmoqda yoki to'langan", "Order is busy"),
}


class PaymeError(Exception):
    def __init__(self, code: int, data: str | None = None) -> None:
        super().__init__(code)
        self.code, self.data = code, data


def error_body(code: int, request_id, data: str | None = None) -> dict:
    ru, uz, en = MESSAGES.get(code, ("Ошибка", "Xato", "Error"))
    return {"error": {"code": code, "message": {"ru": ru, "uz": uz, "en": en}, "data": data}, "id": request_id}


def authorized(header: str) -> bool:
    key = get_settings().payme_key
    if not key or not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return login == "Paycom" and hmac.compare_digest(password, key)


def _ms(dt: datetime | None) -> int:
    return int(dt.timestamp() * 1000) if dt else 0


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


async def _order(session: AsyncSession, params: dict) -> Payment:
    order_id = str((params.get("account") or {}).get("order_id", ""))
    if not order_id.isdigit():
        raise PaymeError(ERR_ORDER_NOT_FOUND, "order_id")
    payment = await session.get(Payment, int(order_id), with_for_update=True)
    if payment is None or payment.provider != "payme":
        raise PaymeError(ERR_ORDER_NOT_FOUND, "order_id")
    if payment.status != "pending":
        raise PaymeError(ERR_ORDER_BUSY, "order_id")
    if int(params.get("amount", -1)) != payment.amount * 100:
        raise PaymeError(ERR_AMOUNT, "amount")
    return payment


async def _by_txn(session: AsyncSession, txn_id: str) -> Payment:
    payment = await session.scalar(
        select(Payment).where(Payment.provider == "payme", Payment.provider_txn_id == txn_id).with_for_update()
    )
    if payment is None:
        raise PaymeError(ERR_NOT_FOUND)
    return payment


def _cancel(payment: Payment, reason: int) -> None:
    payment.state = -2 if payment.state == 2 else -1
    payment.status = "cancelled"
    payment.cancel_time = datetime.now(UTC)
    payment.cancel_reason = reason


def _expired(payment: Payment) -> bool:
    return (
        payment.provider_create_time is not None and _now_ms() - payment.provider_create_time > TRANSACTION_TIMEOUT_MS
    )


def _txn_view(payment: Payment) -> dict:
    return {
        "create_time": payment.provider_create_time or 0,
        "perform_time": _ms(payment.perform_time),
        "cancel_time": _ms(payment.cancel_time),
        "transaction": str(payment.id),
        "state": payment.state,
        "reason": payment.cancel_reason,
    }


async def check_perform(session: AsyncSession, params: dict) -> dict:
    payment = await _order(session, params)
    if payment.provider_txn_id and payment.state == 1:
        raise PaymeError(ERR_ORDER_BUSY, "order_id")
    return {"allow": True}


async def create_transaction(session: AsyncSession, params: dict) -> dict:
    txn_id = str(params["id"])
    existing = await session.scalar(
        select(Payment).where(Payment.provider == "payme", Payment.provider_txn_id == txn_id).with_for_update()
    )
    if existing is not None:
        if existing.state != 1:
            raise PaymeError(ERR_CANNOT_PERFORM)
        if _expired(existing):
            _cancel(existing, REASON_TIMEOUT)
            raise PaymeError(ERR_CANNOT_PERFORM)
        return {"create_time": existing.provider_create_time, "transaction": str(existing.id), "state": 1}
    payment = await _order(session, params)
    if payment.provider_txn_id and payment.provider_txn_id != txn_id:
        raise PaymeError(ERR_ORDER_BUSY, "order_id")  # bu buyurtma uchun boshqa tranzaksiya kutilmoqda
    payment.provider_txn_id = txn_id
    payment.state = 1
    payment.provider_create_time = int(params.get("time") or _now_ms())
    return {"create_time": payment.provider_create_time, "transaction": str(payment.id), "state": 1}


async def perform_transaction(session: AsyncSession, params: dict) -> dict:
    payment = await _by_txn(session, str(params["id"]))
    if payment.state == 1:
        if _expired(payment):
            _cancel(payment, REASON_TIMEOUT)
            raise PaymeError(ERR_CANNOT_PERFORM)
        payment.state = 2
        payment.status = "paid"
        payment.perform_time = datetime.now(UTC)
        shop = await session.get(Shop, payment.shop_id)
        await activate_subscription(session, shop, payment.plan or "start", payment.months or 1)
    elif payment.state != 2:
        raise PaymeError(ERR_CANNOT_PERFORM)
    return {"transaction": str(payment.id), "perform_time": _ms(payment.perform_time), "state": 2}


async def cancel_transaction(session: AsyncSession, params: dict) -> dict:
    payment = await _by_txn(session, str(params["id"]))
    if payment.state == 1:
        _cancel(payment, int(params.get("reason") or 0))
    elif payment.state == 2:
        raise PaymeError(ERR_CANNOT_CANCEL)  # obuna allaqachon berilgan
    return {"transaction": str(payment.id), "cancel_time": _ms(payment.cancel_time), "state": payment.state}


async def check_transaction(session: AsyncSession, params: dict) -> dict:
    return _txn_view(await _by_txn(session, str(params["id"])))


async def get_statement(session: AsyncSession, params: dict) -> dict:
    start, end = int(params.get("from", 0)), int(params.get("to", 0))
    rows = await session.scalars(
        select(Payment)
        .where(
            Payment.provider == "payme",
            Payment.provider_txn_id.is_not(None),
            Payment.provider_create_time >= start,
            Payment.provider_create_time <= end,
        )
        .order_by(Payment.provider_create_time)
    )
    return {
        "transactions": [
            {
                "id": p.provider_txn_id,
                "time": p.provider_create_time,
                "amount": p.amount * 100,
                "account": {"order_id": str(p.id)},
                **_txn_view(p),
            }
            for p in rows
        ]
    }


METHODS = {
    "CheckPerformTransaction": check_perform,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
}


async def handle(session: AsyncSession, body: dict) -> dict:
    request_id = body.get("id")
    method = METHODS.get(body.get("method", ""))
    if method is None:
        return error_body(ERR_METHOD, request_id)
    try:
        result = await method(session, body.get("params") or {})
    except PaymeError as exc:
        await session.commit()  # bekor qilish (timeout) kabi o'zgarishlar saqlanadi
        return error_body(exc.code, request_id, exc.data)
    await session.commit()
    return {"result": result, "id": request_id}
