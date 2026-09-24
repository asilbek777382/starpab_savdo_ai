import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aiop:aiop@localhost:5432/aiop_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["BOT_USERNAME"] = "test_operator_bot"
os.environ["WEBHOOK_SECRET"] = "hook-secret"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["VOYAGE_API_KEY"] = ""
os.environ["STT_API_URL"] = ""
os.environ["DEBOUNCE_SECONDS"] = "0"
os.environ["COOKIE_SECURE"] = "false"
os.environ["PUBLIC_WEB_URL"] = "https://navbatchi.test"
os.environ["SECRET_KEY"] = "test-secret-key-for-jwt-signing-32b"

import pytest  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.runtime import Runtime, set_runtime  # noqa: E402
from tests.fakes import FakeBot, FakeLLM  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    db.set_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_db(engine):
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def redis():
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def session(engine):
    async with db.get_sessionmaker()() as s:
        yield s


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
async def fake_bot():
    bot = FakeBot()
    yield bot
    await bot.session.close()


@pytest.fixture
async def runtime(redis, fake_llm, fake_bot):
    rt = Runtime(redis=redis, llm=fake_llm, bot=fake_bot, arq=None, embedder=None)
    set_runtime(rt)
    yield rt
    set_runtime(None)
