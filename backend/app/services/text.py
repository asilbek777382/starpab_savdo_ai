"""Matnni qidiruv uchun normallashtirish: kirill → lotin, apostroflar, kichik harf.

O'zbek (lotin/kirill) va rus yozuvlari aralash kelgani uchun hamma narsa bitta lotin
ko'rinishga keltiriladi, shunda trigram qidiruv yozuvdan qat'i nazar ishlaydi.
"""

import re

_CYR = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ъ": "",
    "ы": "i",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "қ": "q",
    "ғ": "g",
    "ў": "o",
    "ҳ": "h",
}
_APOSTROPHES = re.compile(r"[’‘ʻʼ`´']")
_NON_WORD = re.compile(r"[^0-9a-z]+")


def translit(text: str) -> str:
    return "".join(_CYR.get(ch, ch) for ch in text.lower())


def normalize(text: str) -> str:
    """'Қора ко‘йлак' va "qora ko'ylak" → 'qora koylak'."""
    text = translit(text or "")
    text = _APOSTROPHES.sub("", text)
    return _NON_WORD.sub(" ", text).strip()
