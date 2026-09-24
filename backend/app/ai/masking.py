"""Telefon raqamlarini LLM'ga yubormaslik uchun maskalash.

Mijoz yozgan raqam [PHONE_1] ko'rinishida LLM'ga boradi, asl qiymat esa
conversation.contact["phones"] ichida saqlanadi va create_order paytida qo'yiladi.
"""

import re

PHONE_RE = re.compile(r"(?<!\d)(?:\+?998[\s\-]?)?\(?(\d{2})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})(?!\d)")
TOKEN_RE = re.compile(r"\[PHONE_\d+\]")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    if len(digits) == 9:
        return "+998" + digits
    return None


class PhoneMasker:
    def __init__(self, phones: dict[str, str] | None = None) -> None:
        self.phones: dict[str, str] = dict(phones or {})

    def _token_for(self, phone: str) -> str:
        for token, value in self.phones.items():
            if value == phone:
                return token
        token = f"[PHONE_{len(self.phones) + 1}]"
        self.phones[token] = phone
        return token

    def mask(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            phone = normalize_phone(m.group(0))
            return self._token_for(phone) if phone else m.group(0)

        return PHONE_RE.sub(repl, text or "")

    def add(self, phone: str) -> str | None:
        normalized = normalize_phone(phone)
        return self._token_for(normalized) if normalized else None

    def unmask(self, value: str) -> str | None:
        """Token yoki oddiy raqamdan haqiqiy normallashgan raqamni qaytaradi."""
        value = (value or "").strip()
        if TOKEN_RE.fullmatch(value):
            return self.phones.get(value)
        return normalize_phone(value)
