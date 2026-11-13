import pytest

from chess_backend.classify import Thresholds, classify_loss


def test_threshold_boundaries_are_configurable():
    rules = Thresholds(inaccuracy=40, mistake=90, blunder=180)
    assert [classify_loss(cp, rules) for cp in (0, 39, 40, 89, 90, 179, 180)] == [
        "none", "none", "inaccuracy", "inaccuracy", "mistake", "mistake", "blunder"]


def test_thresholds_must_increase():
    with pytest.raises(ValueError, match="threshold"):
        Thresholds(inaccuracy=100, mistake=90, blunder=200)


def test_mate_comparison_does_not_fabricate_cp_loss():
    assert classify_loss(None, Thresholds(), best_mate=1, played_mate=None) == "blunder"
    assert classify_loss(None, Thresholds(), best_mate=None, played_mate=-2) == "blunder"
    assert classify_loss(None, Thresholds(), best_mate=1, played_mate=1) == "none"
    assert classify_loss(None, Thresholds(), best_mate=3, played_mate=5) == "unclassified_mate"
