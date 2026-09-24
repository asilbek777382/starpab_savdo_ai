"""Embedding provayderi (ixtiyoriy). Kalit berilmasa semantik qidiruv o'chadi va faqat trigram ishlaydi."""

from typing import Protocol

import httpx

from app.config import get_settings


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], input_type: str) -> list[list[float]]: ...


class VoyageEmbeddings:
    url = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        self.api_key, self.model, self.dim = api_key, model, dim

    async def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": texts, "model": self.model, "input_type": input_type, "output_dimension": self.dim},
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]


def get_embedding_provider() -> EmbeddingProvider | None:
    s = get_settings()
    if s.voyage_api_key:
        return VoyageEmbeddings(s.voyage_api_key, s.embedding_model, s.embedding_dim)
    return None
