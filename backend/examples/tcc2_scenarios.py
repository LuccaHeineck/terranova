"""Run the real May 2024 scenarios the TCC II figures need and cache their results.

`examples/tcc2_figures.py` plots from these caches, so the figures can be
re-styled without re-running the model. Each scenario is the same gauge-driven
run `examples/validate_may2024.py` scores (real terrain, roughness, hydrograph,
north-edge inflow, south-edge outlet, from a dry grid to the observed peak),
plus the per-step history and per-cell products a figure needs: dt and the
mass balance at every step, the gauge cell's water surface, depth snapshots at
whole days, each cell's first-wet time and the maximum-depth envelope.

The loop is a trimmed duplicate of `validate_may2024.py`'s `_run_to_peak` (which
itself duplicates `api/routers/simulations.py::_run_gauge_driven`), for the same
reason that one gives: nothing imports `examples/`.

Scenarios (wall-clock uncontended, NumPy):
    temporal_90m_moore      the validated configuration, outflow_fraction=0.085 (~8 min)
    temporal_90m_vonneumann the unvalidated 4-neighbor option, same settings (~5 min)
    temporal_90m_baseline   the step-10 baseline, outflow_fraction=0.5 (~23 min)
    temporal_60m_moore      the 60m resolution check, outflow_fraction=0.085 (~21 min)
    temporal_30m_moore      the live API's 30m grid, outflow_fraction=0.085 (hours; section 26)

Results go to `data/processed/tcc2/<scenario>.npz` (gitignored with the rest of
`data/processed/`). A scenario whose cache exists is skipped unless `--force`.

Run from the backend/ directory with the venv active:

    python -m examples.tcc2_scenarios [--scenario NAME ...] [--force]
"""

import argparse
import time

import numpy as np

from config import settings
from ingestion.dem import build_elevation_matrix
from ingestion.flood_extent import build_observed_flood_mask, build_validation_reference
from ingestion.hydrograph import (
    build_hydrograph,
    discharge_to_inflow,
    find_boundary_inflow_mask,
    find_boundary_outlet,
    load_raw_stage_series,
)
from ingestion.landcover import build_roughness_matrix
from simulation.engine import DEFAULT_OUTFLOW_FRACTION, compute_stable_dt, outflow_fraction_for_dt, step
from validation.metrics import confusion_counts, csi

CACHE_DIR = settings.PROCESSED_DIR / "tcc2"

# Same wet-cell cutoff as validate_may2024.py and the frontend.
FLOODED_DEPTH_THRESHOLD_M = 0.01

# Depth snapshots for the flood-sequence figure, in simulated hours; the peak
# itself (133.5 h) is always saved as the final H.
SNAPSHOT_HOURS = (24, 48, 72, 96, 120)

SCENARIOS = {
    "temporal_90m_moore": {"resolution": 90, "outflow_fraction": DEFAULT_OUTFLOW_FRACTION, "neighborhood": "moore"},
    "temporal_90m_vonneumann": {"resolution": 90, "outflow_fraction": DEFAULT_OUTFLOW_FRACTION, "neighborhood": "von_neumann"},
    "temporal_90m_baseline": {"resolution": 90, "outflow_fraction": 0.5, "neighborhood": "moore"},
    "temporal_60m_moore": {"resolution": 60, "outflow_fraction": DEFAULT_OUTFLOW_FRACTION, "neighborhood": "moore"},
    "temporal_30m_moore": {"resolution": 30, "outflow_fraction": DEFAULT_OUTFLOW_FRACTION, "neighborhood": "moore"},
}


def run_scenario(name: str, resolution: int, outflow_fraction: float, neighborhood: str) -> None:
    grid = settings.SCORED_GRIDS[resolution]
    dx = float(resolution)
    Z = build_elevation_matrix(processed_path=grid["dem_path"], resolution=dx)
    N = build_roughness_matrix(reference_path=grid["dem_path"], processed_path=grid["landcover_path"])
    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)

    elapsed_seconds, stage_m = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_elapsed_seconds = float(elapsed_seconds[int(np.argmax(stage_m))])
    gauge_row, gauge_col = grid["gauge_cell"]
    cell_area_m2 = dx**2
    print(f"[{name}] grid {Z.shape} at {dx:.0f}m, outflow_fraction={outflow_fraction}, {neighborhood}")

    H = np.zeros_like(Z)
    first_wet_s = np.full(Z.shape, np.nan)
    max_depth = np.zeros_like(Z)
    snapshots = {}
    pending_snapshots = [h * 3600.0 for h in SNAPSHOT_HOURS]

    history = {key: [] for key in ("elapsed_s", "dt_s", "dt_cfl_s", "discharge_m3s", "volume", "cum_inflow", "cum_outflow", "gauge_wse_m", "flooded_cells")}
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    start = time.perf_counter()
    while elapsed_time < peak_elapsed_seconds:
        dt_cfl = compute_stable_dt(Z, H, N, dx, neighborhood=neighborhood)
        dt = min(dt_cfl, 900.0)
        dt = min(dt, peak_elapsed_seconds - elapsed_time)

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        volume_before = H.sum()
        H = step(
            Z,
            H,
            N,
            outflow_fraction=outflow_fraction_for_dt(outflow_fraction, dt, dt_cfl),
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
            neighborhood=neighborhood,
        )
        cumulative_outflow += volume_before + inflow.sum() - H.sum()
        cumulative_inflow += inflow.sum()
        elapsed_time += dt
        t += 1

        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        expected_volume = cumulative_inflow - cumulative_outflow
        assert abs(H.sum() - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), f"volume drifted at step {t}"

        wet = H > FLOODED_DEPTH_THRESHOLD_M
        newly_wet = wet & np.isnan(first_wet_s)
        first_wet_s[newly_wet] = elapsed_time
        np.maximum(max_depth, H, out=max_depth)
        while pending_snapshots and elapsed_time >= pending_snapshots[0]:
            snapshots[pending_snapshots.pop(0)] = H.copy()

        history["elapsed_s"].append(elapsed_time)
        history["dt_s"].append(dt)
        history["dt_cfl_s"].append(dt_cfl)
        history["discharge_m3s"].append(discharge)
        history["volume"].append(float(H.sum()))
        history["cum_inflow"].append(cumulative_inflow)
        history["cum_outflow"].append(cumulative_outflow)
        history["gauge_wse_m"].append(float(Z[gauge_row, gauge_col] + H[gauge_row, gauge_col]))
        history["flooded_cells"].append(int(wet.sum()))

        if t % 20_000 == 0:
            print(f"  [{name}] step {t}: {elapsed_time / 3600:.1f} h of {peak_elapsed_seconds / 3600:.1f} h")
    wall_clock_s = time.perf_counter() - start

    simulated = H > FLOODED_DEPTH_THRESHOLD_M
    observed = build_observed_flood_mask(reference_path=grid["dem_path"], processed_path=grid["flood_extent_path"])
    _, excluded = build_validation_reference(Z, reference_path=grid["dem_path"], gauge_row=gauge_row, gauge_col=gauge_col)
    valid = ~excluded
    tp, fp, fn = confusion_counts(simulated[valid], observed[valid])
    print(
        f"[{name}] peak after {t} steps, {wall_clock_s / 60:.1f} min; naive CSI {csi(simulated, observed):.4f}, "
        f"gap-only {tp}/{fp}/{fn} CSI {csi(simulated[valid], observed[valid]):.4f}"
    )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_seconds = np.array(sorted(snapshots))
    np.savez_compressed(
        CACHE_DIR / f"{name}.npz",
        Z=Z,
        N=N,
        H=H,
        first_wet_s=first_wet_s,
        max_depth=max_depth,
        snapshot_seconds=snapshot_seconds,
        snapshots=np.stack([snapshots[s] for s in snapshot_seconds]),
        observed=observed,
        excluded=excluded,
        inflow_mask=inflow_mask,
        outlet_mask=np.isfinite(boundary_elevation[-1, 1:-1]),
        gauge_cell=np.array([gauge_row, gauge_col]),
        peak_elapsed_s=peak_elapsed_seconds,
        steps=t,
        wall_clock_s=wall_clock_s,
        resolution=resolution,
        outflow_fraction=outflow_fraction,
        neighborhood=neighborhood,
        **{key: np.array(values) for key, values in history.items()},
    )
    print(f"[{name}] cached to {CACHE_DIR / f'{name}.npz'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", nargs="+", choices=sorted(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--force", action="store_true", help="re-run scenarios whose cache already exists")
    args = parser.parse_args()
    for name in args.scenario:
        if (CACHE_DIR / f"{name}.npz").exists() and not args.force:
            print(f"[{name}] cached, skipping (--force to re-run)")
            continue
        run_scenario(name, **SCENARIOS[name])


if __name__ == "__main__":
    main()
