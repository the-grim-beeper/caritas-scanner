"""The score (spec §2.5):

    signal_score = authority × regional_relevance × novelty × consequence × forward_lag

`consequence` (for social provision and coordination in Landkreis Miesbach) replaces the
template's economic_materiality; the other four factors are unchanged.

Multiplicative on purpose — a retrospective item (forward_lag≈0) or a duplicate
(novelty=0) cannot be rescued by the other factors. All five are stored so the UI
shows the decomposition, never a bare product."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreComponents:
    authority: float
    regional_relevance: float
    novelty: float
    consequence: float
    forward_lag: float


def score(c: ScoreComponents) -> float:
    return c.authority * c.regional_relevance * c.novelty * c.consequence * c.forward_lag


def story_confidence(distinct_sources: int) -> float:
    """Each independent outlet halves the remaining doubt: 0.5, 0.75, 0.875 …"""
    return 1.0 - 0.5 ** max(1, distinct_sources)
