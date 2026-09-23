import numpy as np
import pytest

from validation.metrics import csi, false_alarm_rate, hit_rate

# A tiny 2x3 grid with one of each confusion-matrix outcome, plus a repeat of
# TP/TN so the fractions aren't trivially 1 or 0:
#   (0,0) TP   (0,1) FP   (0,2) FN
#   (1,0) TN   (1,1) TP   (1,2) TN
# -> TP=2, FP=1, FN=1, TN=2
_SIMULATED = np.array([[True, True, False], [False, True, False]])
_OBSERVED = np.array([[True, False, True], [False, True, False]])


def test_csi_matches_hand_computed_value():
    assert csi(_SIMULATED, _OBSERVED) == pytest.approx(2 / 4)


def test_hit_rate_matches_hand_computed_value():
    assert hit_rate(_SIMULATED, _OBSERVED) == pytest.approx(2 / 3)


def test_false_alarm_rate_matches_hand_computed_value():
    assert false_alarm_rate(_SIMULATED, _OBSERVED) == pytest.approx(1 / 3)


def test_csi_raises_when_both_masks_empty():
    empty = np.zeros((2, 3), dtype=bool)
    with pytest.raises(ValueError, match="undefined"):
        csi(empty, empty)


def test_hit_rate_raises_when_no_observed_flooded_cells():
    simulated = np.array([[True, False], [False, False]])
    observed = np.zeros((2, 2), dtype=bool)
    with pytest.raises(ValueError, match="undefined"):
        hit_rate(simulated, observed)


def test_false_alarm_rate_raises_when_no_simulated_flooded_cells():
    simulated = np.zeros((2, 2), dtype=bool)
    observed = np.array([[True, False], [False, False]])
    with pytest.raises(ValueError, match="undefined"):
        false_alarm_rate(simulated, observed)
