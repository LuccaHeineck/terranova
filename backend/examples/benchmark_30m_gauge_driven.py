"""Real wall-clock benchmark of the gauge-driven engine at the committed,
live-API resolution (roadmap step 11, performance benchmarking).

Mirrors `examples/validate_may2024.py`'s scope exactly (real hydrograph, real
outlet, stop at the real observed May 2024 peak) but at
`config.settings.TARGET_RESOLUTION_METERS` (30m, the grid `POST /simulations`
actually serves) instead of the 90m validation shortcut - this is the number
that answers "how long does a real run against the live API's own grid
actually take," not an extrapolation from the smaller validation grid.

Also scores CSI/Hit Rate/False Alarm Rate against the same real SGB
`COTA_3367cm` ground truth, rasterized onto this 30m grid instead of the 90m
one, so the accuracy comparison is on equal footing with what the live API
would actually produce.

A deliberate duplicate of `_run_gauge_driven`'s loop, for the same reason
`validate_may2024.py` already documents (`examples/` can't import from
`api/`). Not wired into any test suite - this is a one-off measurement
script, run manually:

    python -m examples.benchmark_30m_gauge_driven
"""

import time

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
from simulation.engine import compute_stable_dt, outflow_fraction_for_dt, step
from validation.metrics import csi, false_alarm_rate, hit_rate

_FLOODED_DEPTH_THRESHOLD_M = 0.01
_PROGRESS_EVERY_N_STEPS = 5_000


def _require_raw_file(path, download_command: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `.venv/bin/python -m {download_command}` first.")


def _run_to_peak(peak_elapsed_seconds: float) -> None:
    Z = build_elevation_matrix()  # defaults: 30m, DEM_PROCESSED_PATH - the live API's own grid
    N = build_roughness_matrix(reference_path=settings.DEM_PROCESSED_PATH)
    print(f"grid shape at {settings.TARGET_RESOLUTION_METERS:.0f}m resolution: {Z.shape} ({Z.size} cells)")

    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)

    dx = settings.TARGET_RESOLUTION_METERS
    cell_area_m2 = dx**2

    H = np.zeros_like(Z)
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    start = time.perf_counter()
    while elapsed_time < peak_elapsed_seconds:
        dt_cfl = compute_stable_dt(Z, H, N, dx)
        dt = min(dt_cfl, 900.0)
        dt = min(dt, peak_elapsed_seconds - elapsed_time)

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        volume_before = H.sum()
        H = step(
            Z,
            H,
            N,
            outflow_fraction=outflow_fraction_for_dt(0.5, dt, dt_cfl),
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
        )
        cumulative_outflow += volume_before + inflow.sum() - H.sum()
        elapsed_time += dt
        cumulative_inflow += inflow.sum()
        t += 1

        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        expected_volume = cumulative_inflow - cumulative_outflow
        assert abs(H.sum() - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), (
            f"volume drifted at step {t}: {H.sum()} vs {expected_volume}"
        )

        if t % _PROGRESS_EVERY_N_STEPS == 0:
            elapsed_wall = time.perf_counter() - start
            print(
                f"  step {t}: elapsed={elapsed_time / 86400:.2f}d "
                f"({100 * elapsed_time / peak_elapsed_seconds:.1f}% of the way to the peak), "
                f"max depth={H.max():.2f}m, wall={elapsed_wall / 60:.1f} min so far"
            )
    wall_clock = time.perf_counter() - start

    print(f"\nreached the peak after {t} steps, {elapsed_time / 3600:.1f}h simulated, "
          f"{wall_clock / 60:.2f} min ({wall_clock / 3600:.2f} h) wall-clock")
    print(f"mass balance: inflow={cumulative_inflow:.1f}, outflow={cumulative_outflow:.1f}, final H.sum()={H.sum():.1f}")
    print(f"max simulated depth: {H.max():.2f}m")

    simulated_mask = H > _FLOODED_DEPTH_THRESHOLD_M
    observed_mask = build_observed_flood_mask(
        reference_path=settings.DEM_PROCESSED_PATH,
        processed_path=settings.FLOOD_EXTENT_PROCESSED_PATH,
    )

    print(f"simulated flooded cells: {simulated_mask.sum()} of {simulated_mask.size} ({100 * simulated_mask.mean():.1f}%)")
    print(f"observed flooded cells:  {observed_mask.sum()} of {observed_mask.size} ({100 * observed_mask.mean():.1f}%)")
    print(f"CSI:              {csi(simulated_mask, observed_mask):.3f}")
    print(f"Hit Rate:         {hit_rate(simulated_mask, observed_mask):.3f}")
    print(f"False Alarm Rate: {false_alarm_rate(simulated_mask, observed_mask):.3f}")


def main() -> None:
    _require_raw_file(settings.DEM_RAW_PATH, "scripts.download_dem")
    _require_raw_file(settings.LANDCOVER_RAW_PATH, "scripts.download_landcover")
    _require_raw_file(settings.HYDROGRAPH_RAW_PATH, "scripts.download_hydrograph")
    _require_raw_file(settings.FLOOD_EXTENT_RAW_PATH, "scripts.download_flood_extent")

    elapsed_seconds, stage_m = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_index = int(np.argmax(stage_m))
    peak_elapsed_seconds = float(elapsed_seconds[peak_index])
    print(
        f"real observed peak: stage={stage_m[peak_index]:.2f}m at "
        f"{peak_elapsed_seconds / 86400:.2f} days into the record (TCC-documented peak: 33.66m)"
    )

    _run_to_peak(peak_elapsed_seconds)


if __name__ == "__main__":
    main()
