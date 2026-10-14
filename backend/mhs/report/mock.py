"""A Lagebericht shaped exactly like the live one, citing only ids from its input and
using no figure the input does not contain. Deterministic: no key, no model, no money."""
from __future__ import annotations


def _headlines(signals: list[dict], lang: str) -> str:
    open_, close = ("„", "“") if lang == "de" else ('"', '"')
    return "; ".join(f"{open_}{s[f'headline_{lang}']}{close}" for s in signals)


def mock_report(inputs: dict) -> dict:
    signals: list[dict] = inputs["signals"]
    questions: list[dict] = inputs["questions"]
    events: list[dict] = inputs["events"]
    top = signals[:3]

    by_layer: dict[str, list[dict]] = {}
    for s in signals:
        by_layer.setdefault(s["layer"], []).append(s)

    evidenced = [q for q in questions if q["judgements"]]
    q_out = [
        {"question_id": q["id"], "movement": q["movement"],
         "note_de": f"[mock] Belege dieser Woche zu: {q['title_de']}",
         "note_en": f"[mock] This week's evidence on: {q['title_en']}",
         "judgement_ids": [j["id"] for j in q["judgements"]]}
        for q in evidenced
    ]
    busiest = max(evidenced, key=lambda q: len(q["judgements"]), default=None)

    if busiest is not None:
        second_de = (f"Für die Frage der Sozialraumlotsen ist diese Woche die Frage „{busiest['title_de']}“ "
                     "am stärksten belegt.")
        second_en = (f"For the Sozialraumlotsen question, the best-evidenced question this week is "
                     f"\"{busiest['title_en']}\".")
    else:
        second_de = "Für die Frage der Sozialraumlotsen gab es diese Woche keine neuen Belege zu den Beobachtungsfragen."
        second_en = "For the Sozialraumlotsen question, none of the monitoring questions received new evidence this week."

    return {
        "lead_de": f"[mock] Diese Woche oben: {_headlines(top, 'de')}. "
                   "ANTHROPIC_API_KEY setzen für einen analytisch verfassten Lagebericht.",
        "lead_en": f"[mock] Top of the week: {_headlines(top, 'en')}. "
                   "Set ANTHROPIC_API_KEY for an analyst-written report.",
        "questions": q_out,
        "sections": [
            {"layer": layer, "items": [
                {"signal_id": s["id"], "note_de": f"[mock] {s['headline_de'][:120]}",
                 "note_en": f"[mock] {s['headline_en'][:120]}"}
                for s in items[:5]
            ]}
            for layer, items in by_layer.items()
        ],
        "chains": [],
        "watch": [{"event_id": e["id"], "why_de": "[mock] in den nächsten 30 Tagen",
                   "why_en": "[mock] within the next 30 days"} for e in events[:5]],
        "friday_de": f"[mock] Diese Woche sah der Scanner unter anderem: {_headlines(top, 'de')}.\n\n{second_de}",
        "friday_en": f"[mock] This week the scanner saw, among others: {_headlines(top, 'en')}.\n\n{second_en}",
        "friday_signal_ids": [s["id"] for s in top],
    }
