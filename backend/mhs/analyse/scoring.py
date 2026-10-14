"""The brief's score, verbatim:

    signal_score = authority × regional_relevance × novelty × economic_materiality × forward_lag

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
    economic_materiality: float
    forward_lag: float


def score(c: ScoreComponents) -> float:
    return c.authority * c.regional_relevance * c.novelty * c.economic_materiality * c.forward_lag


def story_confidence(distinct_sources: int) -> float:
    """Each independent outlet halves the remaining doubt: 0.5, 0.75, 0.875 …"""
    return 1.0 - 0.5 ** max(1, distinct_sources)
