"""One-time schema rebuild for a database that holds no signals yet.

The first production database was created on 2026-10-14 from the template's older models;
the initial migration builds tables from the current models, so that database had to be
rebuilt once (authorised by Nicklas on 2026-10-15). The rebuild runs only when the deploy
sets RESET_EMPTY_SCHEMA=yes AND the database contains no signals — a forgotten variable can
never wipe a scanner that has collected anything.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def reset_if_empty(dsn: str, *, enabled: bool) -> str:
    if not enabled:
        return "disabled"
    conn = await asyncpg.connect(dsn)
    try:
        if await conn.fetchval("select to_regclass('public.signals')") is not None:
            n = await conn.fetchval("select count(*) from signals")
            if n:
                return f"refused: {n} signals"
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        return "reset"
    finally:
        await conn.close()


async def main() -> None:
    from mhs.config import settings

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    result = await reset_if_empty(dsn, enabled=os.environ.get("RESET_EMPTY_SCHEMA") == "yes")
    print(f"reset_if_empty: {result}")


if __name__ == "__main__":
    asyncio.run(main())
