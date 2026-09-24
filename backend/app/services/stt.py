"""Ovozli xabarni matnga aylantirish (ixtiyoriy). OpenAI-mos /audio/transcriptions endpoint'i bilan ishlaydi."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


async def transcribe(audio: bytes, filename: str = "voice.ogg") -> str | None:
    s = get_settings()
    if not s.stt_api_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                s.stt_api_url,
                headers={"Authorization": f"Bearer {s.stt_api_key}"} if s.stt_api_key else {},
                files={"file": (filename, audio, "audio/ogg")},
                data={"model": s.stt_model},
            )
            resp.raise_for_status()
            return (resp.json().get("text") or "").strip() or None
    except Exception:
        log.exception("STT xatosi")
        return None
