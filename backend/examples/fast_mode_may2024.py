"""Torres-inspired non-temporal fast mode against the real May 2024 event
(hybrid architecture, docs/tcc-deviations.md sections 17 and 19).

Runs `simulation.fast_engine.classify_steady_flood` on exactly the same
setup `examples/validate_may2024.py` scores the temporal engine on - the 90m
validation grid, real terrain/roughness, the real hydrograph, the real
north-edge inflow and south-edge outlet, the real SGB `COTA_3367cm` reference
mask - and reports CSI/Hit Rate/False Alarm Rate both naive and with the
Estrela-gap-only correction (section 16.2), side by side with the temporal
engine's documented calibrated result, plus wall-clock time. That pair of
numbers - accuracy vs. time - is the trade-off data point the hybrid
architecture exists to produce.

Forcing: the steady discharge the real hydrograph gives at the observed peak
(`Hydrograph.discharge_at` at the stage series' `argmax`) - the same
discharge the temporal engine injects at that moment. No time integration.

Comparison is against this project's own temporal engine only. The fast
engine is *inspired by* Torres et al. (2022), not a reproduction of it, so
none of that paper's reported numbers are compared against here.

The Estrela-gap correction reuses
`examples.rescore_stage_invariant.build_validity_masks`, which queries three
SGB stage layers live (network); `--skip-gap-correction` runs fully offline
with naive scoring only.

Run from the backend/ directory with the venv active:

    python -m examples.fast_mode_may2024 [--skip-gap-correction] [--save-masks PATH.npz] [--depth-png PATH.png]
"""

import argparse
import statistics
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from config import settings
from ingestion.dem import build_elevation_matrix
from ingestion.flood_extent import build_observed_flood_mask
from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask, find_boundary_outlet, load_raw_stage_series
from ingestion.landcover import build_roughness_matrix
from simulation.fast_engine import CONVEYING, DRY, EXITING, INUNDATED, classify_steady_flood
from validation.metrics import confusion_counts, csi, false_alarm_rate, hit_rate

# Same wet-cell cutoff as validate_may2024.py, so both engines' extents are
# thresholded identically.
_FLOODED_DEPTH_THRESHOLD_M = 0.01

# The temporal engine's documented result on this same setup at the live
# default outflow_fraction=0.085 (docs/tcc-deviations.md section 16.4 for the
# scores, section 18 for the uncontended 90m wall-clock to the peak). Quoted,
# not re-run here - re-running costs ~8 minutes and reproduces these to within
# one cell (section 18).
_TEMPORAL_NAIVE = {"tp": 789, "fp": 1167, "fn": 42, "csi": 0.3949}
_TEMPORAL_GAP_ONLY_CSI = 0.8997
_TEMPORAL_WALL_CLOCK_S = 7.6 * 60

_TIMING_REPEATS = 20


def _require_raw_file(path, download_command: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `.venv/bin/python -m {download_command}` first.")


def _score(simulated: np.ndarray, observed: np.ndarray) -> dict:
    tp, fp, fn = confusion_counts(simulated, observed)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "csi": csi(simulated, observed),
        "hit_rate": hit_rate(simulated, observed),
        "false_alarm_rate": false_alarm_rate(simulated, observed),
    }


def run(skip_gap_correction: bool, save_masks: Path | None, depth_png: Path | None) -> None:
    total_start = time.perf_counter()
    Z = build_elevation_matrix(
        processed_path=settings.DEM_VALIDATION_PROCESSED_PATH,
        resolution=settings.VALIDATION_RESOLUTION_METERS,
    )
    N = build_roughness_matrix(
        reference_path=settings.DEM_VALIDATION_PROCESSED_PATH,
        processed_path=settings.LANDCOVER_VALIDATION_PROCESSED_PATH,
    )
    dx = settings.VALIDATION_RESOLUTION_METERS
    elapsed_seconds, stage_m = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_index = int(np.argmax(stage_m))
    peak_discharge = build_hydrograph().discharge_at(float(elapsed_seconds[peak_index]))
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)
    print(
        f"grid {Z.shape} at {dx:.0f}m; real observed peak stage {stage_m[peak_index]:.2f}m -> "
        f"steady forcing Q={peak_discharge:.1f} m3/s through {int(inflow_mask.sum())} inflow cells"
    )

    def classify():
        return classify_steady_flood(
            Z,
            N,
            dx,
            peak_discharge,
            inflow_mask,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
            depth_threshold_m=_FLOODED_DEPTH_THRESHOLD_M,
        )

    first_start = time.perf_counter()
    result = classify()
    first_call_s = time.perf_counter() - first_start
    repeat_times = []
    for _ in range(_TIMING_REPEATS):
        t0 = time.perf_counter()
        classify()
        repeat_times.append(time.perf_counter() - t0)
    median_s = statistics.median(repeat_times)

    # Discharge continuity - this engine's analogue of the temporal engine's
    # mass-balance assertion.
    balance = result.outflow_m3s + result.retained_m3s
    assert abs(balance - result.inflow_m3s) <= 1e-9 * result.inflow_m3s, (
        f"discharge continuity violated: in={result.inflow_m3s}, out+retained={balance}"
    )
    print(
        f"continuity: inflow={result.inflow_m3s:.3f} = outflow {result.outflow_m3s:.3f} "
        f"+ retained {result.retained_m3s:.3f} m3/s"
    )
    counts = {name: int((result.state == s).sum()) for name, s in
              [("DRY", DRY), ("CONVEYING", CONVEYING), ("INUNDATED", INUNDATED), ("EXITING", EXITING)]}
    print(f"states: {counts}; conveying cells on the slope floor: {result.min_slope_cells}")
    flooded_depths = result.depth[result.flooded]
    print(
        f"flooded {int(result.flooded.sum())} of {result.flooded.size} cells "
        f"({100 * result.flooded.mean():.1f}%), depth median {np.median(flooded_depths):.2f}m, "
        f"max {result.depth.max():.2f}m"
    )

    observed = build_observed_flood_mask(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH)
    naive = _score(result.flooded, observed)
    gap_only = None
    if not skip_gap_correction:
        # Deferred import: only this path needs the network-backed SGB stage query.
        from examples.rescore_stage_invariant import build_validity_masks

        _, _, valid_gap_only, _ = build_validity_masks(Z)
        gap_only = _score(result.flooded[valid_gap_only], observed[valid_gap_only])
    total_s = time.perf_counter() - total_start

    print("\n=== fast (Torres-inspired, non-temporal) vs temporal engine, 90m, May 2024 peak ===")
    print(f"{'':28s}{'fast':>14s}{'temporal':>14s}")
    print(f"{'naive TP / FP / FN':28s}{naive['tp']:>5d}/{naive['fp']:>4d}/{naive['fn']:>4d}"
          f"{_TEMPORAL_NAIVE['tp']:>5d}/{_TEMPORAL_NAIVE['fp']:>4d}/{_TEMPORAL_NAIVE['fn']:>4d}")
    print(f"{'naive CSI':28s}{naive['csi']:>14.4f}{_TEMPORAL_NAIVE['csi']:>14.4f}")
    print(f"{'naive Hit Rate / FAR':28s}{naive['hit_rate']:>7.3f}/{naive['false_alarm_rate']:.3f}")
    if gap_only is not None:
        print(f"{'Estrela-gap-only TP/FP/FN':28s}{gap_only['tp']:>5d}/{gap_only['fp']:>4d}/{gap_only['fn']:>4d}")
        print(f"{'Estrela-gap-only CSI':28s}{gap_only['csi']:>14.4f}{_TEMPORAL_GAP_ONLY_CSI:>14.4f}")
        print(f"{'gap-only Hit Rate / FAR':28s}{gap_only['hit_rate']:>7.3f}/{gap_only['false_alarm_rate']:.3f}")
    print(f"{'wall-clock (engine only)':28s}{median_s * 1e3:>11.1f} ms{_TEMPORAL_WALL_CLOCK_S / 60:>10.1f} min")
    print(f"  -> {_TEMPORAL_WALL_CLOCK_S / median_s:,.0f}x faster (median of {_TIMING_REPEATS} repeats; "
          f"first call {first_call_s * 1e3:.1f} ms; end-to-end incl. data loading and scoring {total_s:.1f}s)")

    if save_masks is not None:
        save_masks.parent.mkdir(parents=True, exist_ok=True)
        # Same keys validate_may2024.py's --save-masks writes, so
        # plot_confusion_map.py / shift_search_noise_floor.py work on it too.
        np.savez(save_masks, simulated_mask=result.flooded, observed_mask=observed, Z=Z, H=result.depth,
                 state=result.state, discharge=result.discharge)
        print(f"saved masks to {save_masks}")
    if depth_png is not None:
        fig, axes = plt.subplots(1, 2, figsize=(11, 5))
        axes[0].imshow(np.where(result.flooded, result.depth, np.nan), cmap="Blues")
        axes[0].set_title(f"fast mode depth (m), Q={peak_discharge:.0f} m3/s")
        im = axes[1].imshow(result.state, cmap="tab10", vmin=0, vmax=9)
        axes[1].set_title("state: 0 DRY, 1 CONVEYING, 2 INUNDATED, 3 EXITING")
        for ax in axes:
            ax.axis("off")
        fig.colorbar(im, ax=axes[1], shrink=0.7)
        depth_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(depth_png, dpi=100, bbox_inches="tight")
        print(f"saved depth/state visualization to {depth_png}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Torres-inspired fast mode vs. the real May 2024 event (90m).")
    parser.add_argument("--skip-gap-correction", action="store_true",
                        help="naive scoring only - skips the live SGB stage-layer query (runs offline)")
    parser.add_argument("--save-masks", type=Path, default=None)
    parser.add_argument("--depth-png", type=Path, default=None)
    args = parser.parse_args()

    _require_raw_file(settings.DEM_RAW_PATH, "scripts.download_dem")
    _require_raw_file(settings.LANDCOVER_RAW_PATH, "scripts.download_landcover")
    _require_raw_file(settings.HYDROGRAPH_RAW_PATH, "scripts.download_hydrograph")
    _require_raw_file(settings.FLOOD_EXTENT_RAW_PATH, "scripts.download_flood_extent")
    run(args.skip_gap_correction, args.save_masks, args.depth_png)


if __name__ == "__main__":
    main()
