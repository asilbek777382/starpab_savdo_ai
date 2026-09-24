"""Instagram API with Instagram Login (graph.instagram.com).

Xabar yuborish: POST /{version}/me/messages, recipient = mijozning IGSID.
Faqat mijozning oxirgi xabaridan keyin 24 soat ichida javob berish mumkin.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

TEXT_LIMIT = 1000
SCOPES = "instagram_business_basic,instagram_business_manage_messages"

# Testlar httpx.MockTransport o'rnatadi
_transport: httpx.AsyncBaseTransport | None = None


class InstagramError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Instagram API {status}: {message}")
        self.status = status


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, transport=_transport)


def _graph(path: str) -> str:
    s = get_settings()
    return f"{s.ig_graph_url}/{s.ig_graph_version}/{path.lstrip('/')}"


async def _check(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error") or {}
        raise InstagramError(resp.status_code, err.get("message") or resp.text[:200])
    return data


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """Instagram xabari 1000 belgigacha: uzun javob bo'laklarga (iloji bo'lsa qator/gap chegarasida) bo'linadi."""
    text = text.strip()
    parts: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(". ", 0, limit))
        cut = cut + 1 if cut > limit // 2 else limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


class InstagramAPI:
    """Bitta ulangan professional akkaunt tokeni bilan ishlaydi. account_id — webhook'dagi IG_ID."""

    def __init__(self, token: str, account_id: str | None = None) -> None:
        self.token = token
        self.account_id = account_id or "me"

    async def _post_message(self, payload: dict) -> dict:
        async with _client() as c:
            resp = await c.post(
                _graph(f"{self.account_id}/messages"), json=payload, headers={"Authorization": f"Bearer {self.token}"}
            )
        return await _check(resp)

    async def send_text(self, recipient_id: str, text: str) -> list[str]:
        mids = []
        for part in split_text(text):
            data = await self._post_message({"recipient": {"id": recipient_id}, "message": {"text": part}})
            if data.get("message_id"):
                mids.append(data["message_id"])
        return mids

    async def send_image(self, recipient_id: str, url: str) -> str | None:
        data = await self._post_message(
            {"recipient": {"id": recipient_id}, "message": {"attachment": {"type": "image", "payload": {"url": url}}}}
        )
        return data.get("message_id")

    async def typing(self, recipient_id: str) -> None:
        await self._post_message({"recipient": {"id": recipient_id}, "sender_action": "typing_on"})

    async def user_profile(self, igsid: str) -> dict:
        async with _client() as c:
            resp = await c.get(_graph(igsid), params={"fields": "name,username", "access_token": self.token})
        return await _check(resp)

    async def me(self) -> dict:
        async with _client() as c:
            resp = await c.get(_graph("me"), params={"fields": "user_id,username,name", "access_token": self.token})
        return await _check(resp)

    async def subscribe_messages(self) -> None:
        """Shu akkaunt uchun ilovani messages webhook'iga obuna qiladi."""
        async with _client() as c:
            resp = await c.post(
                _graph("me/subscribed_apps"), params={"subscribed_fields": "messages", "access_token": self.token}
            )
        await _check(resp)


# ---------- OAuth (Business Login for Instagram) ----------


def redirect_uri() -> str:
    s = get_settings()
    return f"{(s.public_web_url or s.public_base_url).rstrip('/')}/api/instagram/callback"


def authorize_url(state: str) -> str:
    s = get_settings()
    query = {
        "client_id": s.ig_app_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return f"{s.ig_authorize_url}?{urlencode(query)}"


@dataclass
class LongLivedToken:
    access_token: str
    expires_at: datetime


async def exchange_code(code: str) -> str:
    """Kodni qisqa muddatli (1 soat) tokenga almashtiradi."""
    s = get_settings()
    async with _client() as c:
        resp = await c.post(
            f"{s.ig_oauth_url}/oauth/access_token",
            data={
                "client_id": s.ig_app_id,
                "client_secret": s.ig_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(),
                "code": code,
            },
        )
    data = await _check(resp)
    if isinstance(data.get("data"), list) and data["data"]:
        data = data["data"][0]
    return data["access_token"]


def _long_lived(data: dict) -> LongLivedToken:
    expires_in = int(data.get("expires_in") or 60 * 24 * 3600)
    return LongLivedToken(data["access_token"], datetime.now(UTC) + timedelta(seconds=expires_in))


async def long_lived_token(short_token: str) -> LongLivedToken:
    """Qisqa tokenni ~60 kunlik tokenga almashtiradi."""
    s = get_settings()
    async with _client() as c:
        resp = await c.get(
            f"{s.ig_graph_url}/access_token",
            params={"grant_type": "ig_exchange_token", "client_secret": s.ig_app_secret, "access_token": short_token},
        )
    return _long_lived(await _check(resp))


async def refresh_token(token: str) -> LongLivedToken:
    s = get_settings()
    async with _client() as c:
        resp = await c.get(
            f"{s.ig_graph_url}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token}
        )
    return _long_lived(await _check(resp))
