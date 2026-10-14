"""The one-time schema rebuild runs only when explicitly enabled AND the database holds no
signals — so a forgotten variable can never wipe a scanner that has collected anything."""
import asyncpg
import pytest
from sqlalchemy import text

from scripts.reset_if_empty import reset_if_empty
from tests.conftest import TEST_URL


def _dsn() -> str:
    return TEST_URL.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
async def scratch_db():
    dsn = _dsn().rsplit("/", 1)[0] + "/mhs_test_reset"
    admin = await asyncpg.connect(_dsn().rsplit("/", 1)[0] + "/postgres")
    await admin.execute("DROP DATABASE IF EXISTS mhs_test_reset WITH (FORCE)")
    await admin.execute("CREATE DATABASE mhs_test_reset")
    await admin.close()
    yield dsn


async def test_disabled_does_nothing(scratch_db):
    c = await asyncpg.connect(scratch_db)
    await c.execute("CREATE TABLE sources (id int)")
    await c.close()
    assert await reset_if_empty(scratch_db, enabled=False) == "disabled"
    c = await asyncpg.connect(scratch_db)
    assert await c.fetchval("select to_regclass('public.sources')") is not None
    await c.close()


async def test_refuses_when_signals_exist(scratch_db):
    c = await asyncpg.connect(scratch_db)
    await c.execute("CREATE TABLE signals (id int); INSERT INTO signals VALUES (1)")
    await c.close()
    assert await reset_if_empty(scratch_db, enabled=True) == "refused: 1 signals"
    c = await asyncpg.connect(scratch_db)
    assert await c.fetchval("select count(*) from signals") == 1
    await c.close()


async def test_rebuilds_an_empty_old_schema(scratch_db):
    c = await asyncpg.connect(scratch_db)
    await c.execute("CREATE TABLE signals (id int); CREATE TABLE sources (id int); CREATE TABLE alembic_version (v text)")
    await c.close()
    assert await reset_if_empty(scratch_db, enabled=True) == "reset"
    c = await asyncpg.connect(scratch_db)
    assert await c.fetchval("select count(*) from pg_tables where schemaname='public'") == 0
    await c.close()
