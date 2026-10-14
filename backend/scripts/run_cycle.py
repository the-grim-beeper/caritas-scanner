"""Run one cycle from the command line: `python -m scripts.run_cycle [--report]`
(--report writes the weekly Lagebericht instead of running the daily cycle)."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mhs.cycle import run_cycle, run_report  # noqa: E402
from mhs.db.engine import session_factory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    if "--report" in sys.argv:
        d = await run_report(session_factory())
        print("report:", d.id if d else None, d.model if d else "")
        return
    c = await run_cycle(session_factory())
    print(f"cycle {c.id} mode={c.mode} fetched={c.items_fetched} new={c.items_new} extracted={c.extracted} "
          f"signals={c.signals} stories_new={c.stories_new} corroborations={c.corroborations} "
          f"failed_sources={c.failed_sources} judged={c.judged} judgements={c.judgements} "
          f"edges_new={c.edges_new} error={c.error}")


if __name__ == "__main__":
    asyncio.run(main())
