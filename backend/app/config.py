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
    # Web sayt manzili (magic-link uchun); bo'sh bo'lsa public_base_url ishlatiladi
    public_web_url: str = ""
    cookie_secure: bool = True
    session_days: int = 7
    webhook_secret: str = "change-me-webhook"
    # webhook — Telegram HTTPS manzilga yuboradi; polling — domen/HTTPS yo'q serverlar uchun (alohida bot jarayoni)
    bot_mode: str = "webhook"

    # Instagram (Instagram API with Instagram Login). Meta ilova sozlamalaridan olinadi
    ig_app_id: str = ""
    ig_app_secret: str = ""
    ig_verify_token: str = ""
    ig_graph_version: str = "v26.0"
    ig_graph_url: str = "https://graph.instagram.com"
    ig_oauth_url: str = "https://api.instagram.com"
    ig_authorize_url: str = "https://www.instagram.com/oauth/authorize"

    # Obuna to'lovlari. Payme: Merchant API (JSON-RPC), Click: SHOP API (prepare/complete)
    payme_merchant_id: str = ""
    payme_key: str = ""  # kassa kaliti (Basic auth paroli; login — "Paycom")
    payme_checkout_url: str = "https://checkout.paycom.uz"
    click_service_id: str = ""
    click_merchant_id: str = ""
    click_secret_key: str = ""
    click_pay_url: str = "https://my.click.uz/services/pay"

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

    # TTS — ovozli javoblar (Azure Speech). Kalit bo'lmasa ovozli javob o'chiq
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    tts_voice_uz_female: str = "uz-UZ-MadinaNeural"
    tts_voice_uz_male: str = "uz-UZ-SardorNeural"
    tts_voice_ru_female: str = "ru-RU-SvetlanaNeural"
    tts_voice_ru_male: str = "ru-RU-DmitryNeural"
    tts_max_chars: int = 900

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
