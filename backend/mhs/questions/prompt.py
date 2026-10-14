"""The judge prompt. The system block — rules plus the fifteen questions, rendered from
the database rows in sort order — is identical bytes on every call and carries the cache
marker; only the batch of signals goes in the user message."""
from __future__ import annotations

from collections.abc import Sequence

from mhs import vocab
from mhs.db.models import Question, Signal

# Enough for the evidence of a press release or a protocol page; the validator still checks
# quotes against the full text.
ORIGINAL_TEXT_CHARS = 5000

RULES = """You are the judge of a horizon scanner for social provision in Landkreis Miesbach, Upper
Bavaria (17 municipalities; above them Bezirk Oberbayern, the Freistaat Bayern and the Bund).
Its readers, Caritas-Zentrum Miesbach and a foresight team, track fifteen standing monitoring
questions from their source-architecture report. All fifteen serve one question: can an
inter-municipal coordination structure for social provision (the "Interkommunale
Sozialraumlotsen") be anchored so that it still works in 2035 and 2040?

You receive a batch of signals the scanner has already extracted from its sources. For each
signal, decide which of the fifteen questions it is evidence on, if any, and in which direction.

DIRECTION
Each question names a concern or a transition. "for" = the signal is evidence for it (the
report's column "evidence for the concern or transition"); "against" = evidence against it or
stabilising (the report's column "evidence against / stabilising"). Take the direction from the
question's own FOR and AGAINST descriptions below, never from whether the news sounds good or
bad: for q03, "for" is good news (Sozialraumlotsen moving into regular governance); for q01,
"for" is bad news (the municipalities' room shrinking).

WHAT COUNTS
- Judge only what the signal text states. No outside knowledge, no inference about what will
  probably follow, no reading between the lines. Each signal stands alone: never combine two
  signals into one judgement.
- Return a judgement only where the signal is evidence for or against a question as the
  report defines it: the text shows a development that matches, or is a clear instance of,
  that question's FOR or AGAINST description. Sharing a topic is not enough.
  - A Kita or care facility opening is evidence on q07 only if the text ties it to demand
    (waiting list, shortfall) or documents added capacity.
  - A council agenda item "Haushalt 2027" is not evidence on q01 until the text states a cut,
    a freeze, a higher levy or a protected budget line.
  - A single job advertisement is not evidence on q06; a post left unfilled, re-advertised
    again, or a service cutting hours for lack of staff is.
  - An announced meeting is not its outcome.
- Most signals bear on zero or one question; a few on two. Returning nothing for a signal is
  the normal case. Over-inclusion is the failure to avoid: a judgement on weak grounds moves a
  question's balance on no evidence.
- At most one judgement per signal and question.
- Place. q01–q14 concern Landkreis Miesbach and its municipalities, providers and bodies. A
  signal from the Bezirk, the Freistaat or the Bund counts in two cases. (a) The question
  itself names that level (Bezirksumlage in q02; state programmes and grants in q12) or the
  text states an effect on the county: judge it at its normal strength. (b) The text states a
  binding change of rules, funding or refinancing that applies to the county's providers,
  municipalities or programmes because it applies statewide or nationwide (a federal cap on
  refinancing provider wages, a new state funding condition, a statutory change to SGB
  benefits): judge it, but never stronger than "weak", since the local effect is not yet
  shown. Debates, studies and opinions from those levels do not count under (b) — only
  decided or formally proposed changes (a bill, a draft, a working paper of the ministry, a
  regulation, a funding guideline). q15 concerns peer models elsewhere (Gemeindeschwester plus,
  Community Nursing, Präventionsketten and comparable coordination structures): "for" = a peer
  model moved into regular financing or permanent structures; "against" = it ended, shrank or
  survives only on temporary bridge money. Signals about other places count only for q15.

QUOTE — checked by machine: a judgement whose quote is not found verbatim in that signal's
text is discarded.
- Copy `quote` verbatim from the signal: one contiguous passage from ONE of its texts (the
  original title, the original text, the scanner headline or the scanner summary — never
  joined across two of them), character for character, at least a full clause of three words
  or more. No ellipses, no paraphrase, no translation, no corrected spelling, no added
  quotation marks.
- The quote must itself show the evidence. Quote the original title or text wherever it
  states it; quote the scanner's German headline or summary only when the original shown
  does not. The quote is in the language of the text, normally German.
- If no passage of the signal shows the evidence, return no judgement.

STRENGTH
- weak: indirect evidence, or one actor's claim, demand, fear or proposal.
- moderate: a concrete local development (a post left empty, a waiting list, a service
  cutting its hours, a project extended for one more year).
- strong: a decision, a budget line, a closure or a formal agreement.
When torn between two strengths, choose the lower.

RATIONALE
rationale_de (German, written first) and rationale_en (English): one or two sentences each,
saying what the quoted fact is and why it counts for or against this question as defined.
State it plainly; do not hedge and do not go beyond the text.

OUTPUT
{"judgements": [...]}: one entry per (signal, question) that the evidence supports, using the
signal ids of the batch (s1, s2, …). An empty list is a valid and common answer.

THE FIFTEEN QUESTIONS
"""


def _question_block(q: Question) -> str:
    return (
        f"{q.id} — {q.title_en}\n"
        f"      DE: {q.title_de}\n"
        f"  Driver: {q.driver_en}\n"
        f"  FOR — \"{q.for_label_en}\" / „{q.for_label_de}“: {q.for_en}\n"
        f"      DE: {q.for_de}\n"
        f"  AGAINST — \"{q.against_label_en}\" / „{q.against_label_de}“: {q.against_en}\n"
        f"      DE: {q.against_de}"
    )


def system_text(questions: Sequence[Question]) -> str:
    ordered = sorted(questions, key=lambda q: q.sort)
    return RULES + "\n\n".join(_question_block(q) for q in ordered) + "\n"


def system_blocks(questions: Sequence[Question]) -> list[dict]:
    return [{"type": "text", "text": system_text(questions), "cache_control": {"type": "ephemeral"}}]


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …[gekürzt]"


def _signal_block(local_id: str, s: Signal) -> str:
    src = s.source
    item = s.feed_item
    layer = f"{src.layer} — {vocab.LAYERS[src.layer].en}" if src and src.layer in vocab.LAYERS else (
        src.layer if src else "unknown")
    lines = [
        f'<signal id="{local_id}">',
        f"Source: {src.name if src else 'unknown'} (layer: {layer})",
        f"Published: {s.published_at.date().isoformat() if s.published_at else 'unknown'}",
    ]
    if item is not None:
        if item.outlet:
            lines.append(f"Outlet: {item.outlet}")
        lines.append(f"Original title: {(item.title or '').strip() or '(none)'}")
        lines.append(f"Original text:\n{_clip(item.summary, ORIGINAL_TEXT_CHARS) or '(none)'}")
    else:
        lines.append("Original: (not available)")
    lines.append(f"Scanner headline (DE): {s.headline_de}")
    if s.summary_de:
        lines.append(f"Scanner summary (DE): {s.summary_de}")
    lines.append("</signal>")
    return "\n".join(lines)


def user_message(batch: Sequence[tuple[str, Signal]]) -> str:
    head = (f"Read these {len(batch)} signals against the fifteen questions. "
            'Return {"judgements": []} if none of them is evidence on any question.\n\n')
    return head + "\n\n".join(_signal_block(lid, s) for lid, s in batch)
