from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://aiop:aiop@localhost:5432/aiop"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"

    # Telegram
    bot_token: str = ""
    bot_username: str = ""
    public_base_url: str = ""
    webhook_secret: str = "change-me-webhook"

    # LLM (hujjat: arzon/tez model bilan boshlash, murakkabda kuchliroqqa o'tish)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"
    llm_fallback_model: str = "claude-sonnet-5"
    llm_max_tokens: int = 2048
    llm_max_tool_iterations: int = 6
    # USD per 1M token, xarajat hisobi uchun
    llm_price_in: float = 1.0
    llm_price_out: float = 5.0
    usd_to_uzs: float = 12_700.0

    # Embeddings (ixtiyoriy; bo'sh bo'lsa faqat trigram qidiruv)
    voyage_api_key: str = ""
    embedding_model: str = "voyage-3.5"
    embedding_dim: int = 1024

    # STT (ixtiyoriy; OpenAI-mos /audio/transcriptions endpoint)
    stt_api_url: str = ""
    stt_api_key: str = ""
    stt_model: str = "whisper-1"

    # Suhbat sozlamalari
    debounce_seconds: float = 2.5
    history_full_messages: int = 20
    customer_msgs_per_minute: int = 10
    shop_daily_token_limit: int = 2_000_000
    default_handoff_silence_minutes: int = 30
    trial_days: int = 14
    small_catalog_threshold: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
