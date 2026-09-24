"""Suhbatni odamga (sotuvchiga) uzatish."""

import re
from datetime import UTC, datetime, timedelta

from app.models import Conversation, Message, ShopSettings
from app.services.text import normalize

# Normallashtirilgan (lotin) ko'rinishda; kirill va rus yozuvlari ham translit orqali shu yerga tushadi
HANDOFF_KEYWORDS = (
    "operator",
    "menejer",
    "menedjer",
    "odam bilan",
    "jonli odam",
    "chelovek",
    "jivoy",
    "shikoyat",
    "jaloba",
    "qaytarib",
    "pulimni qaytar",
    "pulni qaytar",
    "vozvrat",
    "vernite dengi",
)

HANDOFF_REPLY = {
    "uz": "Savolingizni menejerga yubordim, tez orada javob beradi.",
    "uz_cyrl": "Саволингизни менежерга юбордим, тез орада жавоб беради.",
    "ru": "Передал ваш вопрос менеджеру, он скоро ответит.",
}
DEFAULT_HANDOFF_HOURS = 2


# Kirill yozuvida o'zbek va rus tilini ajratish uchun tipik so'zlar (maxsus harf bo'lmagan qisqa matnlar uchun)
_UZ_CYR_WORDS = frozenset(
    (
        "салом ассалому алайкум бор йўқ йук керак нарх нархи қанча канча рахмат раҳмат ха ҳа мен сиз биз "
        "буюртма илтимос яхши бўлади булади олмоқчиман оламан қандай кандай манзил етказиб бериш учун билан "
        "эмас ва ҳам хам"
    ).split()
)
_RU_WORDS = frozenset(
    (
        "здравствуйте привет есть как что это нет да спасибо пожалуйста сколько можно хочу где когда доставка "
        "цена стоит размер заказ у вас в на и"
    ).split()
)
_WORD = re.compile(r"[а-яёқғўҳ]+")


def detect_script(text: str) -> str:
    """'uz' (lotin), 'uz_cyrl' (o'zbek kirill) yoki 'ru'."""
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
    if cyr * 2 < len([ch for ch in text if ch.isalpha()]):
        return "uz"
    low = text.lower()
    uz_score = 3 * sum(low.count(ch) for ch in "қғўҳ")
    ru_score = 3 * sum(low.count(ch) for ch in "ыщ")
    for word in _WORD.findall(low):
        uz_score += 2 * (word in _UZ_CYR_WORDS)
        ru_score += 2 * (word in _RU_WORDS)
    return "uz_cyrl" if uz_score > ru_score else "ru"


def handoff_reply_for(text: str) -> str:
    return HANDOFF_REPLY[detect_script(text)]


def wants_human(text: str, extra_keywords: list[str] | None = None) -> bool:
    norm = f" {normalize(text)} "
    keywords = [*HANDOFF_KEYWORDS, *(normalize(k) for k in extra_keywords or [])]
    return any(f" {kw}" in norm for kw in keywords if kw)


def mark_handoff(conv: Conversation, settings: ShopSettings, hours: float | None = None) -> None:
    rules = settings.handoff_rules or {}
    hours = hours if hours is not None else float(rules.get("handoff_hours", DEFAULT_HANDOFF_HOURS))
    conv.status = "human"
    conv.stage = "handoff"
    conv.human_until = datetime.now(UTC) + timedelta(hours=hours)


def mark_staff_takeover(conv: Conversation, settings: ShopSettings, silence_minutes: int) -> None:
    """Sotuvchi o'zi chatda yozdi: AI shu suhbatda sozlangan vaqt jim turadi."""
    minutes = int((settings.handoff_rules or {}).get("silence_minutes", silence_minutes))
    conv.status = "human"
    conv.human_until = datetime.now(UTC) + timedelta(minutes=minutes)


def ai_may_reply(conv: Conversation) -> bool:
    if conv.status == "ai":
        return True
    if conv.status == "human" and conv.human_until and conv.human_until <= datetime.now(UTC):
        conv.status = "ai"
        conv.human_until = None
        if conv.stage == "handoff":
            conv.stage = "discovery"
        return True
    return False


HANDOFF_EVENT_PREFIX = "handoff:"


def handoff_event(conv: Conversation, reason: str) -> Message:
    """Statistika uchun tizim yozuvi (LLM tarixiga kirmaydi)."""
    return Message(
        shop_id=conv.shop_id,
        conversation_id=conv.id,
        role="system",
        content=f"{HANDOFF_EVENT_PREFIX} {reason}",
        answered=True,
    )
