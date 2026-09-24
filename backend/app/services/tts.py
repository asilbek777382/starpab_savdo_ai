"""Ovozli javoblar (matn → nutq). Azure Speech neyron ovozlari: o'zbek va rus.

Natija OGG/Opus — Telegram ovozli xabari uchun tayyor format, qo'shimcha konvertatsiya kerak emas.
"""

import logging
import re
from typing import Protocol
from xml.sax.saxutils import escape

import httpx

from app.config import get_settings
from app.services.handoff import detect_script

log = logging.getLogger(__name__)

OUTPUT_FORMAT = "ogg-24khz-16bit-mono-opus"
_transport: httpx.AsyncBaseTransport | None = None  # testlar uchun

_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️‍]")
_MARKUP = re.compile(r"[*_`#>]+")

# O'zbek kirill → lotin (1995 yilgi alifbo). Ovoz modeli lotin yozuvda yaxshiroq o'qiydi.
_UZ_CYR = {
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
    "ъ": "ʼ",
    "ь": "",
    "ы": "i",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ў": "oʻ",
    "қ": "q",
    "ғ": "gʻ",
    "ҳ": "h",
}


def uz_cyr_to_lat(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        lat = _UZ_CYR.get(low)
        if lat is None:
            out.append(ch)
            continue
        if low == "е" and (i == 0 or not text[i - 1].isalpha()):
            lat = "ye"  # so'z boshidagi "е" — "ye" (ер → yer)
        out.append(lat.capitalize() if ch.isupper() and lat else lat)
    return "".join(out)


def clean_for_speech(text: str) -> str:
    text = _EMOJI.sub("", text)
    text = _MARKUP.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def voice_for(text: str, gender: str) -> tuple[str, str, str]:
    """Qaytaradi: (til kodi, ovoz nomi, o'qiladigan matn)."""
    s = get_settings()
    male = gender == "male"
    script = detect_script(text)
    if script == "ru":
        return "ru-RU", s.tts_voice_ru_male if male else s.tts_voice_ru_female, text
    spoken = uz_cyr_to_lat(text) if script == "uz_cyrl" else text
    return "uz-UZ", s.tts_voice_uz_male if male else s.tts_voice_uz_female, spoken


def build_ssml(text: str, lang: str, voice: str) -> str:
    return f"<speak version='1.0' xml:lang='{lang}'><voice name='{voice}'>{escape(text)}</voice></speak>"


class TTSProvider(Protocol):
    async def synthesize(self, text: str, gender: str = "female") -> bytes | None: ...


class AzureTTS:
    def __init__(self, key: str, region: str) -> None:
        self.key, self.region = key, region

    async def synthesize(self, text: str, gender: str = "female") -> bytes | None:
        text = clean_for_speech(text)
        if not text:
            return None
        lang, voice, spoken = voice_for(text, gender)
        async with httpx.AsyncClient(timeout=30, transport=_transport) as client:
            resp = await client.post(
                f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                content=build_ssml(spoken, lang, voice).encode(),
                headers={
                    "Ocp-Apim-Subscription-Key": self.key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                    "User-Agent": "navbatchi-ai",
                },
            )
        if resp.status_code != 200 or not resp.content:
            log.warning("Azure TTS xatosi %s: %s", resp.status_code, resp.text[:200])
            return None
        return resp.content


def get_tts() -> TTSProvider | None:
    s = get_settings()
    if s.azure_speech_key and s.azure_speech_region:
        return AzureTTS(s.azure_speech_key, s.azure_speech_region)
    return None


def should_speak(voice_mode: str, customer_sent_voice: bool) -> bool:
    return voice_mode == "always" or (voice_mode == "on_voice" and customer_sent_voice)
