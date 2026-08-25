from rns.analyse.scoring import ScoreComponents, score, story_confidence


def test_score_is_the_briefs_product_and_zero_when_any_factor_is_zero():
    # Wrong: a weighted sum, which would let a retrospective item (forward_lag=0) score.
    c = ScoreComponents(authority=1.0, regional_relevance=0.8, novelty=0.5, economic_materiality=0.5, forward_lag=0.0)
    assert score(c) == 0.0
    c2 = ScoreComponents(authority=0.7, regional_relevance=1.0, novelty=1.0, economic_materiality=0.5, forward_lag=1.0)
    assert abs(score(c2) - 0.35) < 1e-9


def test_confidence_halves_the_remaining_doubt_per_distinct_source():
    assert story_confidence(1) == 0.5
    assert story_confidence(2) == 0.75
    assert story_confidence(3) == 0.875
