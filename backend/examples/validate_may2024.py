"""Real end-to-end CSI validation of the CA engine against the real May 2024
Taquari flood event (roadmap step 10).

Runs the real gauge-driven engine (steps 8-9, plus the outlet boundary
condition) from a dry grid up through the real observed peak of the May 2024
event, then scores the resulting simulated flooded-cell mask against SGB/
CPRM's real HEC-RAS-2D-modeled flood-extent polygon for that same peak stage
(`ingestion.flood_extent`, `validation.metrics`) - the actual deliverable
this roadmap step is judged on, not a synthetic proxy.

**Runs at `settings.VALIDATION_RESOLUTION_METERS` (90m), not the
officially-served 30m grid.** A deliberate wall-clock tradeoff for this
one-off validation script (a full 30m gauge-driven run takes hours - see
step 9's known limitations in docs/project-plan.md); documented in
docs/tcc-deviations.md. Builds its own separate `data/processed/*_90m.tif`
files and never touches `lajeado_estrela_z.tif`/`_n.tif`, which the live API
depends on.

**Stops at the real observed peak, not the full ~14-day event.** The peak's
elapsed time is found directly from the real gauge stage series itself
(`argmax`), not hardcoded from the TCC's cited 33.66m - printed as a sanity
check against that documented value. Running to the peak (rather than the
full event) is enough to compare against the one ground-truth stage layer
this project has (`COTA_3367cm`) and avoids the multi-hour tail of the event
this step doesn't need.

**The gauge-driven loop below is a deliberate, trimmed duplicate of
`api/routers/simulations.py::_run_gauge_driven`, not a shared function.**
`_run_gauge_driven` is an async WebSocket coroutine inside `api/`, which
`examples/` must never import (`docs/ARCHITECTURE.md`'s dependency
direction only allows `examples/` -> `simulation/`/`ingestion/`/`config/`).
Duplicating a trimmed synchronous version here is the same kind of choice
`docs/project-plan.md` already flags for `poc_grid.py`/`poc_real_dem.py`'s
own independent loops - named explicitly here, not a silent gap.

Run from the backend/ directory with the venv active (expect on the order of
tens of thousands of engine steps / ~20 minutes wall-clock, based on an
earlier ad-hoc 90m run through the same peak):

    python -m examples.validate_may2024
"""

import argparse
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from config import settings
from ingestion.dem import build_elevation_matrix
from ingestion.flood_extent import build_observed_flood_mask
from ingestion.hydrograph import (
    build_hydrograph,
    discharge_to_inflow,
    find_boundary_inflow_mask,
    find_boundary_outlet,
    load_raw_stage_series,
)
from ingestion.landcover import build_roughness_matrix
from simulation.engine import (
    NEIGHBORHOODS,
    VON_NEUMANN_MAX_OUTFLOW_FRACTION,
    compute_stable_dt,
    outflow_fraction_for_dt,
    step,
)
from validation.metrics import csi, false_alarm_rate, hit_rate

# A cell counts as "flooded" above this depth - a documented wet-cell cutoff
# avoiding float-residue false positives (H is real physical meters here, per
# ingestion.hydrograph.discharge_to_inflow's cell_area_m2 convention), not a
# claim about detectable real-world flood depth.
_FLOODED_DEPTH_THRESHOLD_M = 0.01

_PROGRESS_EVERY_N_STEPS = 5_000

# Deliberately NOT simulation.engine.DEFAULT_OUTFLOW_FRACTION (the live default,
# 0.085): an unflagged run of this script keeps reproducing the original step-10
# baseline (CSI 0.133) for comparison rather than silently drifting to a
# different number - see docs/tcc-deviations.md section 16.4. Pass
# --outflow-fraction to score any other value, including the live default.
_STEP10_BASELINE_OUTFLOW_FRACTION = 0.5

# How many equal-width windows to split the last 20% of elapsed time into for
# the gauge-cell WSE rise-rate trend (see _rise_rate_windows below) - matches
# the window count/placement a prior (undocumented) diagnostic used, after an
# earlier attempt with much finer windows (fractions of a percent) misread
# short-term noise as a plateau. Kept as a module constant, not a CLI flag,
# so every variant of a sweep uses an identical, comparable windowing scheme.
_RISE_RATE_N_WINDOWS = 5
_RISE_RATE_SEGMENT_FRACTION = 0.8  # start of the segment, as a fraction of peak_elapsed_seconds

# Manning normal-depth seed for --seed-baseflow-depth (one-off experiment, see
# docs/tcc-deviations.md and this run's own plan notes): estimates a physically
# plausible pre-flood channel depth WITHOUT touching the real gauge's absolute
# stage or the DEM's absolute elevation - the vertical datum tying those two
# together is confirmed unresolved (settings.py's VALIDATION_GAUGE_ROW/COL
# comment, docs/tcc-deviations.md #16). Instead this derives depth purely from
# discharge + slope + roughness, the same Manning relationship the engine
# itself already uses for physical (non-relative-weight) quantities in
# compute_stable_dt's v = (1/n) h^(2/3) sqrt(S).
#
# Q: the rating curve's lowest calibrated discharge (ingestion.hydrograph's
# stage_to_discharge flat-clip) - the real, ANA-measured value this project
# already assigns to the entire pre-flood baseline period.
_SEED_BASEFLOW_DISCHARGE_M3S = 2251.8
# n: MANNING_N_BY_CLASS[33] (open water) - confirmed the actual N value at the
# gauge cell and its channel-floor neighbors on the 90m validation grid.
_SEED_MANNING_N = 0.04
# S: no usable LOCAL slope exists at the gauge - the DEM is exactly flat
# (Z=13.0m) for the ~6.5km traced channel reach around it, an artifact of
# fill_sinks's priority-flood raising this low-gradient floodplain interior to
# a uniform pour-point elevation. Using the best available DEM-grounded proxy
# instead: the whole-domain average slope from the north inflow edge's min
# elevation (12.0m) to the south outlet edge's min elevation (11.0m) over the
# full traced flow-path length (8093.7m) - a domain-scale, not reach-scale,
# estimate, explicitly flagged as a limitation of this one-off test.
_SEED_DOMAIN_AVG_SLOPE = 1.0 / 8093.7
# W: no channel-width/cross-section data or precedent exists anywhere in this
# project (discharge_to_inflow's own docstring notes there's "no data to
# justify" a cross-section assumption). Using the one concrete cross-section
# data point available: at the gauge's own row (row 20), the channel-floor
# cells span 5 contiguous 90m cells (cols 27-31).
_SEED_CHANNEL_WIDTH_M = 5 * 90.0
# Which cells get seeded: reuses ingestion.hydrograph's
# _CHANNEL_ELEVATION_MARGIN_METERS precedent (2.0m of the local minimum counts
# as "channel"), applied across the whole grid instead of one boundary edge.
_SEED_CHANNEL_ELEVATION_MARGIN_M = 2.0


def _manning_normal_depth_m(discharge_m3s: float, n: float, slope: float, width_m: float) -> float:
    """Normal (steady, uniform-flow) depth for a wide rectangular channel, from
    Manning's equation `Q = (W/n) * h^(5/3) * sqrt(S)` solved for `h` - the
    same Manning relationship documented in docs/tcc-summary.md and
    implemented in simulation.engine, just solved for depth given a known
    discharge instead of used as a per-step outflow-direction weight.
    """
    return (discharge_m3s * n / (width_m * slope**0.5)) ** 0.6


def _checkerboard_roughness(H: np.ndarray) -> float:
    """Mean absolute deviation of each wet cell's depth from its own 8-cell
    Moore-neighbor average - the exact metric backend/tests/test_engine.py's
    checkerboard/speckle regressions use, reused here as a numeric stability
    proxy on the real grid. NOT compared against that test's calibrated 0.05
    absolute cutoff (calibrated on a small synthetic grid at a different
    depth scale) - report the raw value and compare it to another variant's
    own value on this same real grid instead.
    """
    rows, cols = H.shape
    padded = np.pad(H, 1, mode="edge")
    neighbor_sum = np.zeros((rows, cols))
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neighbor_sum += padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
    neighbor_mean = neighbor_sum / 8.0
    flooded = H > 1e-6
    if not flooded.any():
        return float("nan")
    return float(np.abs(H[flooded] - neighbor_mean[flooded]).mean())


def _rise_rate_windows(
    elapsed_time_history: np.ndarray,
    wse_history: np.ndarray,
    peak_elapsed_seconds: float,
) -> list[dict]:
    """Gauge-cell WSE rise rate over `_RISE_RATE_N_WINDOWS` equal windows
    spanning the last `1 - _RISE_RATE_SEGMENT_FRACTION` of elapsed time -
    several hours wide at this event's real timescale, not fractions of a
    percent (that finer windowing was tried first in the diagnostic this
    reuses and misread short-term noise as a plateau)."""
    segment_start = _RISE_RATE_SEGMENT_FRACTION * peak_elapsed_seconds
    edges = np.linspace(segment_start, peak_elapsed_seconds, _RISE_RATE_N_WINDOWS + 1)
    wse_at_edges = np.interp(edges, elapsed_time_history, wse_history)

    windows = []
    for i in range(_RISE_RATE_N_WINDOWS):
        start_s, end_s = float(edges[i]), float(edges[i + 1])
        wse_start, wse_end = float(wse_at_edges[i]), float(wse_at_edges[i + 1])
        duration_days = (end_s - start_s) / 86400
        rate_m_per_day = (wse_end - wse_start) / duration_days if duration_days > 0 else float("nan")
        windows.append(
            {
                "start_day": start_s / 86400,
                "end_day": end_s / 86400,
                "wse_start_m": wse_start,
                "wse_end_m": wse_end,
                "rate_m_per_day": rate_m_per_day,
            }
        )
    return windows


def _rise_rate_verdict(windows: list[dict]) -> str:
    """PLATEAUED if the final window's rate has decayed to <=10% of the peak
    rate seen among the windows, else STILL_RISING. A starting heuristic, not
    an authoritative cutoff - always report the full per-window table
    alongside this verdict so a human can judge the trend directly, the same
    posture the project already takes toward _checkerboard_roughness's own
    threshold."""
    rates = [w["rate_m_per_day"] for w in windows if w["rate_m_per_day"] == w["rate_m_per_day"]]  # drop NaN
    if not rates:
        return "UNKNOWN"
    peak_rate = max(abs(r) for r in rates)
    final_rate = rates[-1]
    if peak_rate <= 0:
        return "UNKNOWN"
    return "PLATEAUED" if abs(final_rate) <= 0.10 * peak_rate else "STILL_RISING"


def _require_raw_file(path, download_command: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `.venv/bin/python -m {download_command}` first.")


def _run_to_peak(
    peak_elapsed_seconds: float,
    outlet_drop_m: float | None = None,
    base_outflow_fraction: float = _STEP10_BASELINE_OUTFLOW_FRACTION,
    seed_baseflow_depth: bool = False,
    results_json: Path | None = None,
    save_masks: Path | None = None,
    depth_png: Path | None = None,
    neighborhood: str = "moore",
) -> None:
    """`outlet_drop_m` overrides `find_boundary_outlet`'s `drop_m` (the outlet's
    fixed drainage margin) when given - a single, isolated lever for exploratory
    calibration (see docs/project-plan.md's outlet-margin sweep entry). Omitted
    (None, the default), this reproduces the exact default behavior - no import
    of the private default constant needed here. `find_boundary_outlet`'s other
    parameter, `margin_m` (which boundary cells count as "channel"), is
    deliberately left untouched either way, so the same outlet cells are used
    across every sweep variant.

    `base_outflow_fraction` overrides the base value passed into
    `outflow_fraction_for_dt` each step (default `_STEP10_BASELINE_OUTFLOW_FRACTION`,
    0.5 - the step-10 baseline, not the live default) - the interior-redistribution-rate lever swept in the
    outflow_fraction sweep (see docs/project-plan.md). A second, independent
    isolated lever from `outlet_drop_m` above.

    `seed_baseflow_depth` (default False, reproducing today's dry-grid `H=0` exactly) seeds `H`
    with a Manning-equation normal-depth estimate in channel cells instead - see
    `_manning_normal_depth_m` and the `_SEED_*` constants above for the full derivation and its
    caveats. A one-off experimental lever, not a calibrated production feature.

    `results_json`/`save_masks`/`depth_png` are optional sweep-tooling hooks:
    when given, persist the scored metrics (as JSON), the simulated/observed
    masks plus terrain and gauge-cell history (as an .npz), and a quick depth
    visualization (as a PNG, for the mandatory visual stability check) so a
    later noise-floor check or plot doesn't need to re-run the simulation. All
    three are no-ops when omitted.
    """
    Z = build_elevation_matrix(
        processed_path=settings.DEM_VALIDATION_PROCESSED_PATH,
        resolution=settings.VALIDATION_RESOLUTION_METERS,
    )
    N = build_roughness_matrix(
        reference_path=settings.DEM_VALIDATION_PROCESSED_PATH,
        processed_path=settings.LANDCOVER_VALIDATION_PROCESSED_PATH,
    )
    print(f"grid shape at {settings.VALIDATION_RESOLUTION_METERS:.0f}m resolution: {Z.shape}")

    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    outlet_kwargs = {} if outlet_drop_m is None else {"drop_m": outlet_drop_m}
    boundary_elevation, boundary_roughness = find_boundary_outlet(
        Z, N, settings.HYDROGRAPH_OUTLET_EDGE, **outlet_kwargs
    )

    dx = settings.VALIDATION_RESOLUTION_METERS
    cell_area_m2 = dx**2

    H = np.zeros_like(Z)
    if seed_baseflow_depth:
        depth_m = _manning_normal_depth_m(
            _SEED_BASEFLOW_DISCHARGE_M3S, _SEED_MANNING_N, _SEED_DOMAIN_AVG_SLOPE, _SEED_CHANNEL_WIDTH_M
        )
        print(
            f"Manning normal-depth seed: Q={_SEED_BASEFLOW_DISCHARGE_M3S:.1f}m3/s, n={_SEED_MANNING_N}, "
            f"S={_SEED_DOMAIN_AVG_SLOPE:.2e} (domain-average proxy, not a local reach slope), "
            f"W={_SEED_CHANNEL_WIDTH_M:.0f}m -> depth={depth_m:.2f}m"
        )
        channel_mask = Z <= Z.min() + _SEED_CHANNEL_ELEVATION_MARGIN_M
        H[channel_mask] = depth_m
        print(
            f"seeded {int(channel_mask.sum())} channel cells (Z <= {Z.min() + _SEED_CHANNEL_ELEVATION_MARGIN_M:.1f}m) "
            f"with {depth_m:.2f}m initial depth ({H.sum():.1f} m3-equivalent volume) - a rough, one-off "
            "sanity-check estimate derived from Manning's equation + baseline discharge, NOT a resolved "
            "physical value (domain-average slope proxy, single-cross-section width assumption)."
        )
    initial_volume = float(H.sum())
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    gauge_row, gauge_col = settings.VALIDATION_GAUGE_ROW, settings.VALIDATION_GAUGE_COL
    elapsed_time_history = [0.0]
    wse_history = [float(Z[gauge_row, gauge_col] + H[gauge_row, gauge_col])]

    start = time.perf_counter()
    while elapsed_time < peak_elapsed_seconds:
        # dt_cfl kept separate from the capped dt below, mirroring
        # api/routers/simulations.py::_run_gauge_driven - see that function's
        # comment and simulation.engine.outflow_fraction_for_dt's docstring.
        dt_cfl = compute_stable_dt(Z, H, N, dx, neighborhood=neighborhood)
        dt = min(dt_cfl, 900.0)  # raw feed's own typical sample spacing - see _run_gauge_driven's comment
        dt = min(dt, peak_elapsed_seconds - elapsed_time)  # land exactly on the peak, never past it

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        volume_before = H.sum()
        H = step(
            Z,
            H,
            N,
            outflow_fraction=outflow_fraction_for_dt(base_outflow_fraction, dt, dt_cfl),
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
            neighborhood=neighborhood,
        )
        cumulative_outflow += volume_before + inflow.sum() - H.sum()
        elapsed_time += dt
        cumulative_inflow += inflow.sum()
        t += 1

        elapsed_time_history.append(elapsed_time)
        wse_history.append(float(Z[gauge_row, gauge_col] + H[gauge_row, gauge_col]))

        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        expected_volume = initial_volume + cumulative_inflow - cumulative_outflow
        assert abs(H.sum() - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), (
            f"volume drifted at step {t}: {H.sum()} vs {expected_volume}"
        )

        if t % _PROGRESS_EVERY_N_STEPS == 0:
            gauge_wse = Z[gauge_row, gauge_col] + H[gauge_row, gauge_col]
            print(
                f"  step {t}: elapsed={elapsed_time / 86400:.2f}d "
                f"({100 * elapsed_time / peak_elapsed_seconds:.1f}% of the way to the peak), "
                f"max depth={H.max():.2f}m, gauge WSE={gauge_wse:.2f}m"
            )
    wall_clock = time.perf_counter() - start

    elapsed_time_history = np.array(elapsed_time_history)
    wse_history = np.array(wse_history)

    print(f"reached the peak after {t} steps, {elapsed_time / 3600:.1f}h simulated, {wall_clock / 60:.1f} min wall-clock")
    print(f"mass balance: inflow={cumulative_inflow:.1f}, outflow={cumulative_outflow:.1f}, final H.sum()={H.sum():.1f}")
    print(f"max simulated depth: {H.max():.2f}m")

    gauge_final_h = float(H[gauge_row, gauge_col])
    gauge_final_wse = float(Z[gauge_row, gauge_col] + gauge_final_h)
    grid_max_depth_wse = float((Z + H).flat[np.argmax(H)])
    print(f"gauge cell ({gauge_row}, {gauge_col}): Z={Z[gauge_row, gauge_col]:.3f}m, H={gauge_final_h:.3f}m, WSE={gauge_final_wse:.3f}m")

    rise_rate_windows = _rise_rate_windows(elapsed_time_history, wse_history, peak_elapsed_seconds)
    rise_rate_verdict = _rise_rate_verdict(rise_rate_windows)
    print(f"gauge WSE rise-rate trend (last 20% of elapsed time, {_RISE_RATE_N_WINDOWS} windows): {rise_rate_verdict}")
    for w in rise_rate_windows:
        print(
            f"  {w['start_day']:.2f}d-{w['end_day']:.2f}d: "
            f"WSE {w['wse_start_m']:.3f} -> {w['wse_end_m']:.3f} (rate={w['rate_m_per_day']:+.3f} m/day)"
        )

    checkerboard_roughness = _checkerboard_roughness(H)
    print(f"checkerboard roughness (final H, lower=smoother): {checkerboard_roughness:.5f}")

    simulated_mask = H > _FLOODED_DEPTH_THRESHOLD_M
    observed_mask = build_observed_flood_mask(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH)

    print(f"simulated flooded cells: {simulated_mask.sum()} of {simulated_mask.size} ({100 * simulated_mask.mean():.1f}%)")
    print(f"observed flooded cells:  {observed_mask.sum()} of {observed_mask.size} ({100 * observed_mask.mean():.1f}%)")
    csi_value = csi(simulated_mask, observed_mask)
    hit_rate_value = hit_rate(simulated_mask, observed_mask)
    false_alarm_rate_value = false_alarm_rate(simulated_mask, observed_mask)
    print(f"CSI:              {csi_value:.3f}")
    print(f"Hit Rate:         {hit_rate_value:.3f}")
    print(f"False Alarm Rate: {false_alarm_rate_value:.3f}")

    if results_json is not None:
        results_json.parent.mkdir(parents=True, exist_ok=True)
        results_json.write_text(
            json.dumps(
                {
                    "outlet_drop_m": outlet_drop_m,
                    "outflow_fraction": base_outflow_fraction,
                    "neighborhood": neighborhood,
                    "seed_baseflow_depth": seed_baseflow_depth,
                    "csi": csi_value,
                    "hit_rate": hit_rate_value,
                    "false_alarm_rate": false_alarm_rate_value,
                    "steps": t,
                    "elapsed_days": elapsed_time / 86400,
                    "wall_clock_min": wall_clock / 60,
                    "max_depth_m": float(H.max()),
                    "percent_flooded_simulated": 100 * float(simulated_mask.mean()),
                    "percent_flooded_observed": 100 * float(observed_mask.mean()),
                    "gauge_row": gauge_row,
                    "gauge_col": gauge_col,
                    "gauge_final_h_m": gauge_final_h,
                    "gauge_final_wse_m": gauge_final_wse,
                    "grid_max_depth_wse_m": grid_max_depth_wse,
                    "rise_rate_windows": rise_rate_windows,
                    "rise_rate_verdict": rise_rate_verdict,
                    "checkerboard_roughness": checkerboard_roughness,
                },
                indent=2,
            )
        )
        print(f"results written to {results_json}")

    if save_masks is not None:
        save_masks.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            save_masks,
            simulated_mask=simulated_mask,
            observed_mask=observed_mask,
            Z=Z,
            H=H,
            outlet_drop_m=np.nan if outlet_drop_m is None else outlet_drop_m,
            outflow_fraction=base_outflow_fraction,
            elapsed_time_history_s=elapsed_time_history,
            wse_history_m=wse_history,
        )
        print(f"masks saved to {save_masks}")

    if depth_png is not None:
        depth_png.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6, 5))
        im = ax.imshow(H, cmap="Blues")
        ax.set_title(f"outflow_fraction={base_outflow_fraction} | roughness={checkerboard_roughness:.4f}")
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(im, ax=ax, label="depth (m)")
        fig.tight_layout()
        fig.savefig(depth_png, dpi=150)
        plt.close(fig)
        print(f"depth PNG saved to {depth_png}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outlet-drop-m",
        type=float,
        default=None,
        help=(
            "Override find_boundary_outlet's drop_m (the outlet's fixed drainage "
            "margin) for this run only - exploratory calibration, see "
            "docs/project-plan.md. Omit to use the existing default unchanged."
        ),
    )
    parser.add_argument(
        "--outflow-fraction",
        type=float,
        default=None,
        help=(
            "Override the base outflow_fraction passed to outflow_fraction_for_dt each "
            "step (default 0.5, the step-10 baseline - not the live 0.085 default) - "
            "exploratory calibration for the interior "
            "redistribution-rate sweep, see docs/project-plan.md. Omit to use the "
            "existing default unchanged."
        ),
    )
    parser.add_argument(
        "--seed-baseflow-depth",
        action="store_true",
        help=(
            "Seed H with a Manning-equation normal-depth estimate in channel cells before the run "
            "starts, instead of the default fully-dry grid - a one-off experiment testing the effect "
            "of a physically-derived pre-flood baseline channel depth (see _manning_normal_depth_m). "
            "Omit for today's H=0 default, unchanged."
        ),
    )
    parser.add_argument(
        "--results-json",
        type=Path,
        default=None,
        help="Write scored metrics (CSI/HR/FAR + run metadata) to this JSON path.",
    )
    parser.add_argument(
        "--save-masks",
        type=Path,
        default=None,
        help="Save the simulated/observed masks, Z, H, and gauge-cell history to this .npz path.",
    )
    parser.add_argument(
        "--depth-png",
        type=Path,
        default=None,
        help="Save a quick imshow of the final depth field to this PNG path (visual stability check).",
    )
    parser.add_argument(
        "--neighborhood",
        choices=list(NEIGHBORHOODS),
        default="moore",
        help=(
            "Engine neighborhood (default moore, the TCC's and the only validated one). von_neumann is the "
            "optional 4-neighbor variant compared in docs/tcc-deviations.md section 22."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    _require_raw_file(settings.DEM_RAW_PATH, "scripts.download_dem")
    _require_raw_file(settings.LANDCOVER_RAW_PATH, "scripts.download_landcover")
    _require_raw_file(settings.HYDROGRAPH_RAW_PATH, "scripts.download_hydrograph")
    _require_raw_file(settings.FLOOD_EXTENT_RAW_PATH, "scripts.download_flood_extent")

    elapsed_seconds, stage_m = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_index = int(np.argmax(stage_m))
    peak_elapsed_seconds = float(elapsed_seconds[peak_index])
    print(
        f"real observed peak: stage={stage_m[peak_index]:.2f}m at "
        f"{peak_elapsed_seconds / 86400:.2f} days into the record "
        "(TCC-documented peak: 33.66m)"
    )

    outflow_fraction = args.outflow_fraction if args.outflow_fraction is not None else _STEP10_BASELINE_OUTFLOW_FRACTION
    if args.neighborhood == "von_neumann" and outflow_fraction > VON_NEUMANN_MAX_OUTFLOW_FRACTION:
        print(
            f"WARNING: outflow_fraction={outflow_fraction} is above VON_NEUMANN_MAX_OUTFLOW_FRACTION="
            f"{VON_NEUMANN_MAX_OUTFLOW_FRACTION}: von Neumann's result there depends on the substep fraction "
            "(docs/tcc-deviations.md section 22). Exploratory only - the API refuses this combination."
        )

    _run_to_peak(
        peak_elapsed_seconds,
        outlet_drop_m=args.outlet_drop_m,
        base_outflow_fraction=args.outflow_fraction if args.outflow_fraction is not None else _STEP10_BASELINE_OUTFLOW_FRACTION,
        seed_baseflow_depth=args.seed_baseflow_depth,
        results_json=args.results_json,
        save_masks=args.save_masks,
        depth_png=args.depth_png,
        neighborhood=args.neighborhood,
    )


if __name__ == "__main__":
    main()
