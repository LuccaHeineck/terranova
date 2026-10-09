"""Backend/outflow_fraction benchmark of the real gauge-driven engine (roadmap
step 11 follow-up: GPU portability research, Q10).

Same scenario as `examples/validate_may2024.py` (90m) and
`examples/benchmark_30m_gauge_driven.py` (30m) - real terrain, real roughness,
real hydrograph, real outlet, stopping at the real observed May 2024 peak - but
parameterized so the same loop can be timed under different `outflow_fraction`
values and array backends (NumPy on CPU, CuPy on GPU, or CuPy with each substep fused
into two kernels - simulation/engine_cupy_fused.py, docs/tcc-deviations.md section 25)
without editing code:

    python -m examples.benchmark_backends --resolution 90 --outflow-fraction 0.5
    python -m examples.benchmark_backends --resolution 30 --max-steps 5000 --backend cupy
    python -m examples.benchmark_backends --resolution 90 --backend cupy-fused

Reports macro step count, the per-macro-step substep-count histogram
(`ceil(f_eff / _MAX_STABLE_SUBSTEP_FRACTION)`, computed here rather than by
instrumenting the engine), per-step wall-clock percentiles, total wall-clock,
and (when run to the peak) CSI/Hit Rate/False Alarm Rate.

A deliberate duplicate of `_run_gauge_driven`'s loop, for the same reason
`validate_may2024.py` documents (`examples/` can't import from `api/`).
Research/benchmark tooling only - not wired into any test suite or the API.
"""

import argparse
import math
import time
from collections import Counter
from pathlib import Path

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
from simulation import engine
from simulation.engine import compute_stable_dt, outflow_fraction_for_dt, step
from validation.metrics import csi, false_alarm_rate, hit_rate

_FLOODED_DEPTH_THRESHOLD_M = 0.01
_PROGRESS_EVERY_N_STEPS = 5_000
# Excluded from per-step percentiles: first-call overhead (CuPy JIT-compiles
# and caches each elementwise kernel on first use; NumPy has a smaller cold-cache
# effect). Still counted in total wall-clock.
_WARMUP_STEPS = 50


def _load_grid(resolution: int):
    if resolution == 90:
        Z = build_elevation_matrix(
            processed_path=settings.DEM_VALIDATION_PROCESSED_PATH,
            resolution=settings.VALIDATION_RESOLUTION_METERS,
        )
        N = build_roughness_matrix(
            reference_path=settings.DEM_VALIDATION_PROCESSED_PATH,
            processed_path=settings.LANDCOVER_VALIDATION_PROCESSED_PATH,
        )
        observed = lambda: build_observed_flood_mask(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH)  # noqa: E731
        return Z, N, float(settings.VALIDATION_RESOLUTION_METERS), observed
    Z = build_elevation_matrix()
    N = build_roughness_matrix(reference_path=settings.DEM_PROCESSED_PATH)
    observed = lambda: build_observed_flood_mask(  # noqa: E731
        reference_path=settings.DEM_PROCESSED_PATH,
        processed_path=settings.FLOOD_EXTENT_PROCESSED_PATH,
    )
    return Z, N, float(settings.TARGET_RESOLUTION_METERS), observed


def run(args: argparse.Namespace) -> None:
    if args.substep_fraction is not None:
        name = "_MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN" if args.neighborhood == "von_neumann" else "_MAX_STABLE_SUBSTEP_FRACTION"
        setattr(engine, name, args.substep_fraction)
    print(f"neighborhood={args.neighborhood} max substep fraction={engine._max_stable_substep_fraction(args.neighborhood)}")
    step_fn = step
    if args.backend.startswith("cupy"):
        import cupy as xp

        to_device, to_host, sync = xp.asarray, xp.asnumpy, xp.cuda.Device().synchronize
        if args.backend == "cupy-fused":
            from simulation import engine_cupy_fused

            step_fn = engine_cupy_fused.step
    else:
        xp = np
        to_device = to_host = lambda a: a  # noqa: E731
        sync = lambda: None  # noqa: E731

    elapsed_seconds, stage_m = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_elapsed_seconds = float(elapsed_seconds[int(np.argmax(stage_m))])

    Z_host, N_host, dx, observed_mask_fn = _load_grid(args.resolution)
    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z_host, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z_host, N_host, settings.HYDROGRAPH_OUTLET_EDGE)
    cell_area_m2 = dx**2
    print(
        f"backend={args.backend} resolution={dx:.0f}m grid={Z_host.shape} ({Z_host.size} cells) "
        f"outflow_fraction={args.outflow_fraction} max_steps={args.max_steps or 'to peak'} "
        f"assert_every={args.assert_every}"
    )

    Z = to_device(Z_host)
    N = to_device(N_host)
    boundary_elevation = to_device(boundary_elevation)
    boundary_roughness = to_device(boundary_roughness)
    # Device-side inflow = scalar * float mask: bit-identical to
    # discharge_to_inflow's `inflow[mask] = total / count` (x * 1.0 == x, x * 0.0 == 0).
    inflow_mask_f = to_device(inflow_mask.astype(np.float64))
    inflow_cell_count = int(inflow_mask.sum())

    H = xp.zeros_like(Z)
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    substeps = Counter()
    step_times = []
    snapshot_steps = set(args.snapshot_steps)
    # Time-matched snapshots: runs with different dt trajectories reach a given step at different simulated
    # times, so comparing them step-for-step compares different moments (docs/tcc-deviations.md section 22).
    pending_snapshot_days = sorted(args.snapshot_days)
    stop_seconds = args.stop_days * 86400 if args.stop_days is not None else None
    t = 0

    sync()
    start = time.perf_counter()
    while (
        elapsed_time < peak_elapsed_seconds
        and (args.max_steps is None or t < args.max_steps)
        and (stop_seconds is None or elapsed_time < stop_seconds)
    ):
        step_start = time.perf_counter()
        dt_cfl = compute_stable_dt(Z, H, N, dx, neighborhood=args.neighborhood)
        dt = min(dt_cfl, 900.0)
        dt = min(dt, peak_elapsed_seconds - elapsed_time)
        f_eff = outflow_fraction_for_dt(args.outflow_fraction, dt, dt_cfl)
        substeps[math.ceil(f_eff / engine._max_stable_substep_fraction(args.neighborhood))] += 1

        discharge = hydrograph.discharge_at(elapsed_time)
        if args.backend.startswith("cupy"):
            injected = discharge * dt / cell_area_m2
            inflow = inflow_mask_f * (injected / inflow_cell_count)
        else:
            inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        check = t % args.assert_every == 0
        if check:
            volume_before = float(H.sum())
            injected_sum = float(inflow.sum())
        H = step_fn(
            Z,
            H,
            N,
            outflow_fraction=f_eff,
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
            neighborhood=args.neighborhood,
        )
        elapsed_time += dt
        t += 1
        if args.perturb_ulp and t == 1:
            # Noise-floor control (section 18's ulp sensitivity): nudge the deepest cell by one ulp.
            H_host = to_host(H).copy()
            idx = np.unravel_index(np.argmax(H_host), H_host.shape)
            H_host[idx] = np.nextafter(H_host[idx], np.inf)
            H = to_device(H_host)

        if check:
            volume_after = float(H.sum())
            cumulative_outflow += volume_before + injected_sum - volume_after
            cumulative_inflow += injected_sum
            h_min = float(H.min())
            assert h_min >= -1e-9, f"negative depth at step {t}: {h_min}"
            if args.assert_every == 1:
                expected_volume = cumulative_inflow - cumulative_outflow
                assert abs(volume_after - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), (
                    f"volume drifted at step {t}: {volume_after} vs {expected_volume}"
                )

        sync()
        step_times.append(time.perf_counter() - step_start)

        while pending_snapshot_days and elapsed_time >= pending_snapshot_days[0] * 86400 and args.snapshot_dir:
            day = pending_snapshot_days.pop(0)
            out = Path(args.snapshot_dir) / (
                f"H_{args.backend}_{dx:.0f}m_f{args.outflow_fraction}_{args.neighborhood}"
                f"_s{engine._max_stable_substep_fraction(args.neighborhood)}_day{day}.npy"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            np.save(out, to_host(H))
            print(f"  snapshot day {day}: step {t}, elapsed={elapsed_time / 86400:.4f}d")

        if t in snapshot_steps and args.snapshot_dir:
            out = Path(args.snapshot_dir) / (
                f"H_{args.backend}_{dx:.0f}m_f{args.outflow_fraction}_{args.neighborhood}"
                f"_s{engine._max_stable_substep_fraction(args.neighborhood)}_step{t}.npy"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            np.save(out, to_host(H))

        if t % _PROGRESS_EVERY_N_STEPS == 0:
            print(
                f"  step {t}: elapsed={elapsed_time / 86400:.2f}d "
                f"({100 * elapsed_time / peak_elapsed_seconds:.1f}% to peak), "
                f"max depth={float(H.max()):.2f}m, wall={(time.perf_counter() - start) / 60:.1f} min"
            )
    wall_clock = time.perf_counter() - start

    reached_peak = elapsed_time >= peak_elapsed_seconds
    timed = np.array(step_times[_WARMUP_STEPS:] or step_times) * 1e3
    print(f"\n{'reached the peak' if reached_peak else 'stopped'} after {t} steps, "
          f"{elapsed_time / 3600:.1f}h simulated ({100 * elapsed_time / peak_elapsed_seconds:.1f}% of peak time), "
          f"{wall_clock:.1f}s ({wall_clock / 60:.2f} min) wall-clock")
    print(f"per-step ms (excl. first {_WARMUP_STEPS}): mean={timed.mean():.3f} p50={np.percentile(timed, 50):.3f} "
          f"p95={np.percentile(timed, 95):.3f}")
    total_substeps = sum(k * v for k, v in substeps.items())
    print(f"substeps: total={total_substeps} mean/step={total_substeps / t:.2f} "
          f"histogram(top)={sorted(substeps.items(), key=lambda kv: -kv[1])[:8]}")
    if args.backend.startswith("cupy"):
        print(f"GPU memory pool used: {xp.get_default_memory_pool().used_bytes() / 1e6:.1f} MB, "
              f"total held: {xp.get_default_memory_pool().total_bytes() / 1e6:.1f} MB")

    H_host = to_host(H)
    print(f"max simulated depth: {H_host.max():.4f}m, final H.sum()={H_host.sum():.6f}")
    if args.save_final:
        np.save(args.save_final, H_host)
    if reached_peak:
        simulated_mask = H_host > _FLOODED_DEPTH_THRESHOLD_M
        observed_mask = observed_mask_fn()
        print(f"simulated flooded cells: {simulated_mask.sum()} of {simulated_mask.size}")
        print(f"observed flooded cells:  {observed_mask.sum()} of {observed_mask.size}")
        print(f"CSI={csi(simulated_mask, observed_mask):.3f} "
              f"HitRate={hit_rate(simulated_mask, observed_mask):.3f} "
              f"FAR={false_alarm_rate(simulated_mask, observed_mask):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resolution", type=int, choices=[30, 90], default=90)
    parser.add_argument("--outflow-fraction", type=float, default=engine.DEFAULT_OUTFLOW_FRACTION)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--backend", choices=["numpy", "cupy", "cupy-fused"], default="numpy")
    parser.add_argument("--neighborhood", choices=list(engine.NEIGHBORHOODS), default="moore")
    parser.add_argument(
        "--substep-fraction", type=float, default=None,
        help="Exploratory: override the chosen neighborhood's max stable substep fraction for this run only "
             "(the von Neumann stability sweep, docs/tcc-deviations.md section 22). Omit for the engine's value.",
    )
    parser.add_argument("--assert-every", type=int, default=1,
                        help="mass/negativity check cadence; >1 skips per-step host syncs")
    parser.add_argument("--snapshot-steps", type=int, nargs="*", default=[])
    parser.add_argument("--snapshot-dir", type=str, default=None)
    parser.add_argument("--snapshot-days", type=float, nargs="*", default=[],
                        help="Also snapshot H at the first step reaching each of these simulated days.")
    parser.add_argument("--stop-days", type=float, default=None, help="Stop once this many simulated days elapse.")
    parser.add_argument("--perturb-ulp", action="store_true",
                        help="Noise-floor control: after step 1, move the deepest cell's depth up by one ulp.")
    parser.add_argument("--save-final", type=str, default=None)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
