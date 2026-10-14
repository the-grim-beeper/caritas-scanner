"""Test database: a separate `mhs_test` database on the same Postgres, created on
demand, schema built from the ORM, every table truncated between tests."""
from __future__ import annotations

import os

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://mhs:mhs@localhost:5441/mhs_test")
ADMIN_DSN = "postgresql://mhs:mhs@localhost:5441/postgres"


async def _ensure_database() -> None:
    # The database named in TEST_DATABASE_URL, so parallel worktrees can each have their own.
    name = make_url(TEST_URL).database
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def engine():
    from mhs.db.models import Base

    await _ensure_database()
    eng = create_async_engine(TEST_URL)
    async with eng.begin() as conn:
        # Wholesale reset: a previous run may have left a differently-named
        # constraint behind, which drop_all cannot see.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    from mhs.db.models import Base

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    """Tests never spend money: a key in backend/.env must not flip them to live."""
    from mhs.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "max_item_age_days", 60)
    monkeypatch.setattr(settings, "max_extractions_per_cycle", 1500)
