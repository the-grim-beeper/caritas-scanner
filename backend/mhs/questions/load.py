"""data/questions.yaml → the questions table. Fifteen questions, q01…q15, each with both
languages of every field; anything else is refused at load time, not discovered in the UI."""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhs.db.models import Question

QUESTION_IDS: list[str] = [f"q{i:02d}" for i in range(1, 16)]

FIELDS: tuple[str, ...] = (
    "title_de", "title_en", "driver_de", "driver_en", "sources_de",
    "for_label_de", "for_label_en", "for_de", "for_en",
    "against_label_de", "against_label_en", "against_de", "against_en",
)


def load_questions(path: str | Path) -> list[dict]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a list of questions")
    ids = [str(q.get("id", "")) if isinstance(q, dict) else "" for q in raw]
    if sorted(ids) != QUESTION_IDS:
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        missing = sorted(set(QUESTION_IDS) - set(ids))
        extra = sorted(set(ids) - set(QUESTION_IDS))
        raise ValueError(f"{path}: need exactly q01…q15 once each (duplicates {dupes}, missing {missing}, unknown {extra})")
    out: list[dict] = []
    for q in raw:
        blank = [f for f in FIELDS if not isinstance(q.get(f), str) or not q[f].strip()]
        if blank:
            raise ValueError(f"{path}: {q['id']} has empty or missing {', '.join(blank)}")
        out.append({"id": q["id"], "sort": int(q["id"][1:]), **{f: q[f].strip() for f in FIELDS}})
    return sorted(out, key=lambda q: q["sort"])


async def upsert_questions(session: AsyncSession, items: list[dict]) -> int:
    """Insert or update by id; never deletes (judgements reference the rows). Returns the
    number of questions created."""
    existing = {q.id: q for q in (await session.execute(select(Question))).scalars()}
    created = 0
    for item in items:
        row = existing.get(item["id"])
        if row is None:
            row = Question(id=item["id"])
            session.add(row)
            created += 1
        row.sort = item["sort"]
        for f in FIELDS:
            setattr(row, f, item[f])
    await session.commit()
    return created
