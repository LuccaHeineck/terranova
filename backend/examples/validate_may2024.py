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

# A cell counts as "flooded" above this depth - a documented wet-cell cutoff
# avoiding float-residue false positives (H is real physical meters here, per
# ingestion.hydrograph.discharge_to_inflow's cell_area_m2 convention), not a
# claim about detectable real-world flood depth.
_FLOODED_DEPTH_THRESHOLD_M = 0.01

_PROGRESS_EVERY_N_STEPS = 5_000


def _require_raw_file(path, download_command: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `.venv/bin/python -m {download_command}` first.")


def _run_to_peak(peak_elapsed_seconds: float) -> None:
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
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)

    dx = settings.VALIDATION_RESOLUTION_METERS
    cell_area_m2 = dx**2

    H = np.zeros_like(Z)
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    start = time.perf_counter()
    while elapsed_time < peak_elapsed_seconds:
        # dt_cfl kept separate from the capped dt below, mirroring
        # api/routers/simulations.py::_run_gauge_driven - see that function's
        # comment and simulation.engine.outflow_fraction_for_dt's docstring.
        dt_cfl = compute_stable_dt(Z, H, N, dx)
        dt = min(dt_cfl, 900.0)  # raw feed's own typical sample spacing - see _run_gauge_driven's comment
        dt = min(dt, peak_elapsed_seconds - elapsed_time)  # land exactly on the peak, never past it

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
            print(
                f"  step {t}: elapsed={elapsed_time / 86400:.2f}d "
                f"({100 * elapsed_time / peak_elapsed_seconds:.1f}% of the way to the peak), "
                f"max depth={H.max():.2f}m"
            )
    wall_clock = time.perf_counter() - start

    print(f"reached the peak after {t} steps, {elapsed_time / 3600:.1f}h simulated, {wall_clock / 60:.1f} min wall-clock")
    print(f"mass balance: inflow={cumulative_inflow:.1f}, outflow={cumulative_outflow:.1f}, final H.sum()={H.sum():.1f}")
    print(f"max simulated depth: {H.max():.2f}m")

    simulated_mask = H > _FLOODED_DEPTH_THRESHOLD_M
    observed_mask = build_observed_flood_mask(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH)

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
        f"{peak_elapsed_seconds / 86400:.2f} days into the record "
        "(TCC-documented peak: 33.66m)"
    )

    _run_to_peak(peak_elapsed_seconds)


if __name__ == "__main__":
    main()
