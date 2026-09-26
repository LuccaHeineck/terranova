"""Registration-shift noise-floor check for a validate_may2024.py CSI score
(roadmap step 10/11 exploratory tooling).

Answers: how much of a given CSI score could be explained by nothing more
than a small pixel-registration offset between the simulated and observed
masks, rather than any real physical difference? Shifts the simulated mask
by every (dy, dx) in [-max_shift, max_shift]^2, rescoring CSI at each offset,
and reports the best.

This is a from-scratch reimplementation of an ad hoc process first run
during the outlet-margin sweep (see docs/tcc-deviations.md section 15) -
that version's script was never saved, only its results were transcribed
into the docs. Small numeric differences from the documented 0.1333 -> 0.2792
jump are possible and not a bug in this script; re-run against the default
outflow_fraction=0.5 / outlet_drop_m=2.0 baseline's own saved masks first to
confirm this reproduces something close to that documented jump before
trusting it on a new variant.

Shifts use pad+crop (cells moved off the grid are dropped, filled with
False), not np.roll - wraparound would spuriously match unrelated far-edge
cells on this small ROI.

Run from the backend/ directory with the venv active:
    python -m examples.shift_search_noise_floor --npz PATH [--max-shift 3] [--results-json PATH]
"""

import argparse
import json
from pathlib import Path

import numpy as np

from validation.metrics import csi


def _shift_mask(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift `mask` by (dy, dx) via pad+crop - cells shifted off the grid are
    dropped (filled False), not wrapped around."""
    rows, cols = mask.shape
    shifted = np.zeros_like(mask, dtype=bool)

    src_r0, src_r1 = max(0, -dy), rows - max(0, dy)
    dst_r0, dst_r1 = max(0, dy), rows - max(0, -dy)
    src_c0, src_c1 = max(0, -dx), cols - max(0, dx)
    dst_c0, dst_c1 = max(0, dx), cols - max(0, -dx)

    if src_r1 > src_r0 and src_c1 > src_c0:
        shifted[dst_r0:dst_r1, dst_c0:dst_c1] = mask[src_r0:src_r1, src_c0:src_c1]
    return shifted


def shift_search(
    simulated_mask: np.ndarray, observed_mask: np.ndarray, max_shift: int = 3
) -> dict:
    """Scores CSI at every (dy, dx) in [-max_shift, max_shift]^2, returning the
    baseline (0,0) score, the best offset/score, and the full offset grid."""
    grid: dict[str, float | None] = {}
    best = {"dy": 0, "dx": 0, "csi": float("-inf")}
    baseline_csi = None

    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            shifted = _shift_mask(simulated_mask, dy, dx)
            try:
                score = csi(shifted, observed_mask)
            except ValueError:
                score = None
            grid[f"{dy},{dx}"] = score
            if dy == 0 and dx == 0:
                baseline_csi = score
            if score is not None and score > best["csi"]:
                best = {"dy": dy, "dx": dx, "csi": score}

    return {
        "max_shift": max_shift,
        "baseline_csi": baseline_csi,
        "best_dy": best["dy"],
        "best_dx": best["dx"],
        "best_csi": best["csi"],
        "grid": grid,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npz", type=Path, required=True, help="Path to a validate_may2024.py --save-masks .npz file.")
    parser.add_argument("--max-shift", type=int, default=3, help="Max shift magnitude to search, in cells (default 3).")
    parser.add_argument("--results-json", type=Path, default=None, help="Write the full result (including the offset grid) to this JSON path.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    data = np.load(args.npz)
    simulated_mask = data["simulated_mask"]
    observed_mask = data["observed_mask"]

    result = shift_search(simulated_mask, observed_mask, max_shift=args.max_shift)

    print(f"baseline (0,0) CSI: {result['baseline_csi']:.4f}")
    print(
        f"best CSI: {result['best_csi']:.4f} at (dy={result['best_dy']}, dx={result['best_dx']}) "
        f"(delta={result['best_csi'] - result['baseline_csi']:+.4f})"
    )

    if args.results_json is not None:
        args.results_json.parent.mkdir(parents=True, exist_ok=True)
        args.results_json.write_text(json.dumps(result, indent=2))
        print(f"results written to {args.results_json}")


if __name__ == "__main__":
    main()
