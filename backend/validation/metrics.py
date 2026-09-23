"""Spatial-extent accuracy metrics comparing a simulated flooded-cell mask
against a real observed one (roadmap step 10).

Pure functions over boolean NumPy arrays - dependency-free like
`simulation/engine.py`, easily unit-testable on tiny synthetic grids with
hand-computed expected values. No file I/O, no CA logic - callers (e.g.
`examples/validate_may2024.py`) are responsible for producing both masks
first (a simulated depth array thresholded to "wet", and
`ingestion.flood_extent.build_observed_flood_mask`'s real ground truth).

All three metrics are standard confusion-matrix counts over the two masks:
- True Positive (TP): flooded in both.
- False Positive (FP): flooded in the simulation only (over-prediction).
- False Negative (FN): flooded in the observation only (under-prediction).
"""

import numpy as np


def _confusion_counts(simulated: np.ndarray, observed: np.ndarray) -> tuple[int, int, int]:
    tp = int(np.logical_and(simulated, observed).sum())
    fp = int(np.logical_and(simulated, ~observed).sum())
    fn = int(np.logical_and(~simulated, observed).sum())
    return tp, fp, fn


def csi(simulated: np.ndarray, observed: np.ndarray) -> float:
    """Critical Success Index: TP / (TP + FP + FN).

    The primary spatial-extent metric (TCC's validation plan) - penalizes
    both under- and over-estimation of the flooded area, unlike a plain hit
    rate. 1.0 is a perfect match, 0.0 is no overlap at all.

    Raises if the denominator is zero (no flooded cells in either mask) -
    CSI is mathematically undefined there, not 0 or 1; fail loud rather than
    return a misleading number (same fail-fast style as
    `ingestion.hydrograph.discharge_to_inflow`'s empty-mask check).
    """
    tp, fp, fn = _confusion_counts(simulated, observed)
    denominator = tp + fp + fn
    if denominator == 0:
        raise ValueError("CSI is undefined: no flooded cells in either mask")
    return tp / denominator


def hit_rate(simulated: np.ndarray, observed: np.ndarray) -> float:
    """Hit Rate (a.k.a. Probability of Detection): TP / (TP + FN).

    Fraction of the real observed flooding the simulation actually caught.
    Raises if there are no observed flooded cells (undefined).
    """
    tp, _, fn = _confusion_counts(simulated, observed)
    denominator = tp + fn
    if denominator == 0:
        raise ValueError("hit rate is undefined: no observed flooded cells")
    return tp / denominator


def false_alarm_rate(simulated: np.ndarray, observed: np.ndarray) -> float:
    """False Alarm Rate: FP / (TP + FP).

    Fraction of the simulation's flooded prediction that wasn't real.
    Raises if there are no simulated flooded cells (undefined).
    """
    tp, fp, _ = _confusion_counts(simulated, observed)
    denominator = tp + fp
    if denominator == 0:
        raise ValueError("false alarm rate is undefined: no simulated flooded cells")
    return fp / denominator
