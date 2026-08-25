"""Run one cycle from the command line: `python -m scripts.run_cycle [--digest-only]`."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rns.cycle import run_cycle, run_digest_only  # noqa: E402
from rns.db.engine import session_factory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    if "--digest-only" in sys.argv:
        d = await run_digest_only(session_factory())
        print("digest:", d.id if d else None)
        return
    c = await run_cycle(session_factory())
    print(f"cycle {c.id} mode={c.mode} fetched={c.items_fetched} new={c.items_new} extracted={c.extracted} "
          f"signals={c.signals} stories_new={c.stories_new} corroborations={c.corroborations} "
          f"failed_sources={c.failed_sources} digest_ok={c.digest_ok} error={c.error}")


if __name__ == "__main__":
    asyncio.run(main())
