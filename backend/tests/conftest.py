"""Test database: a separate `rns_test` database on the same Postgres, created on
demand, schema built from the ORM, every table truncated between tests."""
from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://rns:rns@localhost:5438/rns_test")
ADMIN_DSN = "postgresql://rns:rns@localhost:5438/postgres"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _ensure_database() -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname='rns_test'")
        if not exists:
            await conn.execute("CREATE DATABASE rns_test")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def engine():
    from rns.db.models import Base

    await _ensure_database()
    eng = create_async_engine(TEST_URL)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    from rns.db.models import Base

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)
