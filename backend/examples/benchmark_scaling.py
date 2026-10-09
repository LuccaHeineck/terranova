"""Run time and memory of the CA engine vs. grid size and iteration count, per backend
(roadmap step 11: TCC1's performance comparisons, docs/tcc-deviations.md section 25).

    python -m examples.benchmark_scaling
    python -m examples.benchmark_scaling --sizes 64 128 --real 90 --backends numpy loops
    python -m examples.benchmark_scaling --results-json scaling.json --plot scaling.png

Grids: synthetic square valleys (`--sizes`, the same shape as
tests/test_engine_regression.py's scenario: inflow on a north channel, an outlet on the
south edge, varying roughness) and the real 90/60/30m May 2024 grids (`--real`, real
terrain, roughness, inflow edge and outlet). Each grid is first spun up with the
gauge-driven macro step until it is wet, then timed from that state.

Per grid and backend it reports:
- `step()` alone at the default `outflow_fraction` (9 substeps), median/p95 ms;
- for NumPy, the full macro step (`compute_stable_dt` + `outflow_fraction_for_dt` +
  `step`, as `examples/benchmark_backends.py` runs it);
- the transient peak memory of one `step()` (tracemalloc for NumPy and the loops - both
  NumPy buffers and Python lists are traced; the CuPy memory pool for GPU backends) and
  the resident model arrays.
The `loops` backend (simulation/engine_loops.py) is checked bit-identical to NumPy's
output for the same input before it is timed, so a loop timing never comes from a
wrong result; it is skipped above `--loop-max-cells`.

`--iterations` adds the iteration-count dimension on the real grids: cumulative
wall-clock (untraced run) and tracemalloc current/peak (a second, traced run) at each
checkpoint, from a dry grid at the start of the event, to show run time is linear in
steps and memory does not grow. Projected time to the May 2024 peak uses the measured
step counts (section 18: 90m; section 24: 60m) and, for 30m, an estimate.

Run it uncontended, one benchmark at a time (section 18 measured a concurrent job
slowing NumPy ~3x on this hybrid-core laptop). Research tooling only - not wired into
any test suite or the API.
"""

import argparse
import json
import platform
import time
import tracemalloc
from pathlib import Path

import numpy as np

from config import settings
from simulation import engine, engine_loops
from simulation.engine import DEFAULT_OUTFLOW_FRACTION, compute_stable_dt, outflow_fraction_for_dt

_INFLOW_CAP_SECONDS = 900.0  # api/routers/simulations.py::_run_gauge_driven's cap
_SYNTHETIC_DISCHARGE_M3S = 50.0
_SYNTHETIC_DX_M = 30.0
# Measured steps to the May 2024 peak at the live default outflow_fraction
# (docs/tcc-deviations.md section 18 for 90m, section 24 for 60m). 30m has never been run
# to the peak; it is projected from 60m by the CFL ratio (60/30)^1.5, which section 24
# found close to the measured 90->60 ratio (1.73x vs. 1.84x predicted).
_STEPS_TO_PEAK = {90: (134_639, "measured"), 60: (232_908, "measured"), 30: (round(232_908 * 2**1.5), "estimate")}


class _Grid:
    """Everything one macro step needs, plus where the event clock is."""

    def __init__(self, label, Z, N, dx, inflow_mask, boundary_elevation, boundary_roughness, discharge_at):
        self.label, self.Z, self.N, self.dx = label, Z, N, dx
        self.inflow_mask = inflow_mask
        self.boundary_elevation, self.boundary_roughness = boundary_elevation, boundary_roughness
        self.discharge_at = discharge_at
        self.cells = Z.size

    def inflow(self, elapsed, dt):
        inflow = np.zeros_like(self.Z)
        inflow[self.inflow_mask] = self.discharge_at(elapsed) * dt / (self.inflow_mask.sum() * self.dx**2)
        return inflow

    def macro_step(self, H, elapsed, step_fn=engine.step):
        dt_cfl = compute_stable_dt(self.Z, H, self.N, self.dx)
        dt = min(dt_cfl, _INFLOW_CAP_SECONDS)
        f_eff = outflow_fraction_for_dt(DEFAULT_OUTFLOW_FRACTION, dt, dt_cfl)
        H = step_fn(self.Z, H, self.N, **self.step_kwargs(self.inflow(elapsed, dt), f_eff))
        return H, elapsed + dt

    def step_kwargs(self, inflow, outflow_fraction=DEFAULT_OUTFLOW_FRACTION):
        return dict(
            outflow_fraction=outflow_fraction,
            inflow=inflow,
            boundary_elevation=self.boundary_elevation,
            boundary_roughness=self.boundary_roughness,
        )


def _synthetic_grid(size: int) -> _Grid:
    """test_engine_regression.py's 40x40 valley, scaled so the same shape fills any size."""
    rows = cols = size
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    scale = 40.0 / size
    channel_col = cols / 2 + 6 * np.sin(y * scale / 6) / scale
    Z = 30.0 - 0.5 * y * scale + 0.08 * ((x - channel_col) * scale) ** 2
    N = 0.03 + 0.05 * (np.abs(x - channel_col) * scale > 3)
    half_width = max(1, size // 40)
    inflow_mask = np.zeros((rows, cols), dtype=bool)
    inflow_mask[0, int(channel_col[0, 0]) - half_width: int(channel_col[0, 0]) + half_width + 1] = True
    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    outlet_col = int(channel_col[-1, 0]) + 1
    boundary_elevation[-1, outlet_col - half_width - 1: outlet_col + half_width + 2] = Z[-1].min() - 2.0
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, outlet_col - half_width - 1: outlet_col + half_width + 2] = 0.04
    return _Grid(
        f"synthetic {size}x{size}", Z, N, _SYNTHETIC_DX_M, inflow_mask, boundary_elevation, boundary_roughness,
        lambda elapsed: _SYNTHETIC_DISCHARGE_M3S,
    )


def _real_grid(resolution: int) -> _Grid:
    from ingestion.dem import build_elevation_matrix
    from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask, find_boundary_outlet
    from ingestion.landcover import build_roughness_matrix

    if resolution == 30:
        Z = build_elevation_matrix()
        N = build_roughness_matrix(reference_path=settings.DEM_PROCESSED_PATH)
    else:
        grid = settings.SCORED_GRIDS[resolution]
        Z = build_elevation_matrix(processed_path=grid["dem_path"], resolution=float(resolution))
        N = build_roughness_matrix(reference_path=grid["dem_path"], processed_path=grid["landcover_path"])
    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)
    return _Grid(
        f"real {resolution}m", Z, N, float(resolution), inflow_mask, boundary_elevation, boundary_roughness,
        hydrograph.discharge_at,
    )


def _spin_up(grid: _Grid, steps: int, budget_s: float):
    H, elapsed = np.zeros_like(grid.Z), 0.0
    start = time.perf_counter()
    for done in range(1, steps + 1):
        H, elapsed = grid.macro_step(H, elapsed)
        if time.perf_counter() - start > budget_s:
            break
    return H, elapsed, done


def _time_calls(fn, H, n_calls: int, budget_s: float, warmup: int):
    """Per-call seconds of `H = fn(H)`, excluding `warmup` calls; stops early past `budget_s`."""
    for _ in range(warmup):
        H = fn(H)
    times = []
    start = time.perf_counter()
    for _ in range(n_calls):
        t0 = time.perf_counter()
        H = fn(H)
        times.append(time.perf_counter() - t0)
        if time.perf_counter() - start > budget_s and len(times) >= 3:
            break
    return times


def _traced_peak_bytes(fn):
    """Transient peak memory of one call, above what was allocated before it."""
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline, _ = tracemalloc.get_traced_memory()
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak - baseline


def _stats_ms(times):
    ms = np.array(times) * 1e3
    return {"p50_ms": float(np.median(ms)), "p95_ms": float(np.percentile(ms, 95)), "n": len(ms)}


def _resident_bytes(grid: _Grid, H):
    return int(grid.Z.nbytes + grid.N.nbytes + H.nbytes + grid.boundary_elevation.nbytes + grid.boundary_roughness.nbytes)


def _bench_numpy(grid, H, elapsed, args):
    inflow = grid.inflow(elapsed, _INFLOW_CAP_SECONDS)
    kwargs = grid.step_kwargs(inflow)
    step_fn = lambda h: engine.step(grid.Z, h, grid.N, **kwargs)  # noqa: E731
    repeats = [_stats_ms(_time_calls(step_fn, H, args.timed_steps, args.time_budget_s, args.warmup_steps))
               for _ in range(args.repeats)]
    clock = {"elapsed": elapsed}

    def macro(h):
        h, clock["elapsed"] = grid.macro_step(h, clock["elapsed"])
        return h

    macro_times = _time_calls(macro, H, args.timed_steps, args.time_budget_s, args.warmup_steps)
    return {
        "step": {"p50_ms": float(np.median([r["p50_ms"] for r in repeats])),
                 "p95_ms": float(np.median([r["p95_ms"] for r in repeats])),
                 "n": sum(r["n"] for r in repeats), "repeats": len(repeats)},
        "macro_step": _stats_ms(macro_times),
        "step_peak_bytes": _traced_peak_bytes(lambda: step_fn(H)),
    }


def _bench_loops(grid, H, elapsed, args):
    if grid.cells > args.loop_max_cells:
        return {"skipped": f"{grid.cells} cells > --loop-max-cells {args.loop_max_cells}"}
    kwargs = grid.step_kwargs(grid.inflow(elapsed, _INFLOW_CAP_SECONDS))
    expected = engine.step(grid.Z, H, grid.N, **kwargs)
    t0 = time.perf_counter()
    got = engine_loops.step(grid.Z, H, grid.N, **kwargs)
    first = time.perf_counter() - t0
    if not np.array_equal(got, expected):
        raise AssertionError(f"{grid.label}: loop engine differs from NumPy (max |diff| {np.abs(got - expected).max()})")
    step_fn = lambda h: engine_loops.step(grid.Z, h, grid.N, **kwargs)  # noqa: E731
    times = [first] + _time_calls(step_fn, got, args.loop_steps - 1, args.time_budget_s, 0) if args.loop_steps > 1 else [first]
    result = {"step": _stats_ms(times), "parity": "bit-identical"}
    if grid.cells <= args.loop_memory_max_cells:
        result["step_peak_bytes"] = _traced_peak_bytes(lambda: step_fn(H))
    return result


def _bench_cupy(grid, H, elapsed, args, fused: bool):
    import cupy as cp

    if fused:
        from simulation import engine_cupy_fused

        step_impl = engine_cupy_fused.step
    else:
        step_impl = engine.step
    Z, N = cp.asarray(grid.Z), cp.asarray(grid.N)
    inflow = cp.asarray(grid.inflow(elapsed, _INFLOW_CAP_SECONDS))
    kwargs = dict(
        outflow_fraction=DEFAULT_OUTFLOW_FRACTION,
        inflow=inflow,
        boundary_elevation=cp.asarray(grid.boundary_elevation),
        boundary_roughness=cp.asarray(grid.boundary_roughness),
    )
    sync = cp.cuda.Device().synchronize
    H_dev = cp.asarray(H)
    if fused:
        expected = engine.step(grid.Z, H, grid.N, **grid.step_kwargs(grid.inflow(elapsed, _INFLOW_CAP_SECONDS)))
        got = cp.asnumpy(step_impl(Z, H_dev, N, **kwargs))
        if not np.array_equal(got, expected):
            raise AssertionError(f"{grid.label}: fused CuPy step differs from NumPy (max |diff| {np.abs(got - expected).max()})")

    def step_fn(h):
        h = step_impl(Z, h, N, **kwargs)
        sync()
        return h

    pool = cp.get_default_memory_pool()
    repeats = [_stats_ms(_time_calls(step_fn, H_dev, args.timed_steps, args.time_budget_s, args.warmup_steps))
               for _ in range(args.repeats)]
    return {
        "step": {"p50_ms": float(np.median([r["p50_ms"] for r in repeats])),
                 "p95_ms": float(np.median([r["p95_ms"] for r in repeats])),
                 "n": sum(r["n"] for r in repeats), "repeats": len(repeats)},
        "gpu_pool_used_bytes": int(pool.used_bytes()),
        "gpu_pool_total_bytes": int(pool.total_bytes()),
        **({"parity": "bit-identical"} if fused else {}),
    }


def _iteration_count(grid: _Grid, checkpoints: list[int]):
    """Cumulative wall-clock (untraced) and tracemalloc memory (traced) at each checkpoint, from a dry grid."""
    rows = {c: {"steps": c} for c in checkpoints}
    H, elapsed = np.zeros_like(grid.Z), 0.0
    start = time.perf_counter()
    for t in range(1, max(checkpoints) + 1):
        H, elapsed = grid.macro_step(H, elapsed)
        if t in rows:
            rows[t]["wall_s"] = time.perf_counter() - start
            rows[t]["simulated_h"] = elapsed / 3600
    H, elapsed = np.zeros_like(grid.Z), 0.0
    tracemalloc.start()
    try:
        for t in range(1, max(checkpoints) + 1):
            H, elapsed = grid.macro_step(H, elapsed)
            if t in rows:
                current, peak = tracemalloc.get_traced_memory()
                rows[t]["traced_current_bytes"], rows[t]["traced_peak_bytes"] = current, peak
    finally:
        tracemalloc.stop()
    return [rows[c] for c in checkpoints]


def _print_table(results):
    print(f"\n{'grid':<20}{'cells':>10}  {'backend':<11}{'step p50 ms':>12}{'p95 ms':>10}"
          f"{'macro p50 ms':>14}{'step peak MB':>14}{'x numpy':>10}")
    for r in results:
        numpy_p50 = r["backends"].get("numpy", {}).get("step", {}).get("p50_ms")
        for name, b in r["backends"].items():
            if "skipped" in b:
                print(f"{r['grid']:<20}{r['cells']:>10}  {name:<11}{'skipped':>12}")
                continue
            p50 = b["step"]["p50_ms"]
            macro = b.get("macro_step", {}).get("p50_ms")
            peak = b.get("step_peak_bytes", b.get("gpu_pool_used_bytes"))
            ratio = f"{p50 / numpy_p50:.1f}x" if numpy_p50 else ""
            print(f"{r['grid']:<20}{r['cells']:>10}  {name:<11}{p50:>12.3f}{b['step']['p95_ms']:>10.3f}"
                  f"{(f'{macro:.3f}' if macro else ''):>14}{(f'{peak / 1e6:.2f}' if peak is not None else ''):>14}{ratio:>10}")
        if "time_to_peak" in r:
            p = r["time_to_peak"]
            print(f"{'':<32}projected to the May 2024 peak: {p['steps']:,} steps ({p['steps_source']}) "
                  f"x {p['macro_p50_ms']:.3f} ms = {p['minutes']:.1f} min")
        for row in r.get("iterations", []):
            print(f"{'':<32}{row['steps']:>7,} steps: {row['wall_s']:8.2f}s wall, "
                  f"{row['simulated_h']:7.1f}h simulated, traced current {row['traced_current_bytes'] / 1e6:6.2f} MB, "
                  f"peak {row['traced_peak_bytes'] / 1e6:6.2f} MB")


def _plot(results, path: Path):
    """Log-log ms per step() vs. cells, one line per backend (palette validated with the dataviz
    skill's checker: worst adjacent CVD dE 9.1; ends are direct-labelled for the low-contrast slots)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    styles = {
        "numpy": ("#2a78d6", "o", "NumPy (vectorized)"),
        "loops": ("#eb6834", "s", "Python loops"),
        "cupy": ("#1baf7a", "^", "CuPy"),
        "cupy-fused": ("#eda100", "D", "CuPy, fused kernel"),
    }
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for name, (color, marker, label) in styles.items():
        points = sorted(
            (r["cells"], r["backends"][name]["step"]["p50_ms"])
            for r in results if name in r["backends"] and "step" in r["backends"][name]
        )
        if not points:
            continue
        cells, ms = zip(*points)
        ax.plot(cells, ms, color=color, linewidth=2, marker=marker, markersize=6,
                markeredgecolor="#fcfcfb", markeredgewidth=1.5, label=label, zorder=3)
        ax.annotate(label, (cells[-1], ms[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8, color="#0b0b0b")
    real = [r for r in results if r["grid"].startswith("real")]
    for r in real:
        ax.axvline(r["cells"], color="#d6d5d0", linewidth=1, zorder=1)
        ax.text(r["cells"], 1.02, r["grid"].removeprefix("real "), transform=ax.get_xaxis_transform(),
                ha="center", fontsize=7, color="#52514e")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("grid cells", color="#52514e")
    ax.set_ylabel("ms per step() (median, 9 substeps)", color="#52514e")
    ax.grid(True, which="major", color="#e8e7e3", linewidth=0.8)
    ax.tick_params(which="both", colors="#52514e", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#d6d5d0")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.margins(x=0.15)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    print(f"plot written to {path}")


def run(args: argparse.Namespace) -> None:
    grids = [lambda s=s: _synthetic_grid(s) for s in args.sizes] + [lambda r=r: _real_grid(r) for r in args.real]
    results = []
    for build in grids:
        grid = build()
        H, elapsed, spun = _spin_up(grid, args.spinup_steps, args.time_budget_s)
        print(f"{grid.label}: {grid.Z.shape} = {grid.cells} cells, spun up {spun} steps "
              f"({elapsed / 3600:.1f}h simulated, {(H > 0.01).sum()} wet cells)")
        entry = {"grid": grid.label, "shape": list(grid.Z.shape), "cells": grid.cells,
                 "spinup_steps": spun, "resident_bytes": _resident_bytes(grid, H), "backends": {}}
        for backend in args.backends:
            if backend == "numpy":
                entry["backends"][backend] = _bench_numpy(grid, H, elapsed, args)
            elif backend == "loops":
                entry["backends"][backend] = _bench_loops(grid, H, elapsed, args)
            else:
                try:
                    entry["backends"][backend] = _bench_cupy(grid, H, elapsed, args, fused=backend == "cupy-fused")
                except ImportError as exc:
                    entry["backends"][backend] = {"skipped": f"CuPy unavailable: {exc}"}
            print(f"  {backend}: {entry['backends'][backend].get('step', entry['backends'][backend])}")
        resolution = int(grid.dx) if grid.label.startswith("real") else None
        if resolution and "numpy" in entry["backends"]:
            steps, source = _STEPS_TO_PEAK[resolution]
            macro_ms = entry["backends"]["numpy"]["macro_step"]["p50_ms"]
            entry["time_to_peak"] = {"steps": steps, "steps_source": source, "macro_p50_ms": macro_ms,
                                     "minutes": steps * macro_ms / 60_000}
            if args.iterations:
                entry["iterations"] = _iteration_count(grid, args.iterations)
        results.append(entry)

    _print_table(results)
    if args.results_json:
        payload = {
            "hardware": {"processor": platform.processor(), "machine": platform.machine(),
                         "python": platform.python_version(), "numpy": np.__version__},
            "outflow_fraction": DEFAULT_OUTFLOW_FRACTION,
            "args": {k: v for k, v in vars(args).items() if k not in ("results_json", "plot")},
            "results": results,
        }
        Path(args.results_json).write_text(json.dumps(payload, indent=2))
        print(f"results written to {args.results_json}")
    if args.plot:
        _plot(results, Path(args.plot))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="*", default=[32, 64, 128, 256, 512, 1024, 2048],
                        help="Synthetic square grid sides.")
    parser.add_argument("--real", type=int, nargs="*", choices=[30, 60, 90], default=[90, 60, 30],
                        help="Real May 2024 grids, by resolution in meters.")
    parser.add_argument("--backends", nargs="*", choices=["numpy", "loops", "cupy", "cupy-fused"],
                        default=["numpy", "loops"])
    parser.add_argument("--spinup-steps", type=int, default=200)
    parser.add_argument("--warmup-steps", type=int, default=5, help="Untimed calls before each timed series.")
    parser.add_argument("--timed-steps", type=int, default=50)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--time-budget-s", type=float, default=20.0,
                        help="Cap per spin-up and per timed series (at least 3 timed calls are always kept).")
    parser.add_argument("--loop-steps", type=int, default=3, help="Timed calls of the loop engine.")
    parser.add_argument("--loop-max-cells", type=int, default=70_000)
    parser.add_argument("--loop-memory-max-cells", type=int, default=70_000,
                        help="tracemalloc slows the loop engine several-fold; skip its memory figure above this.")
    parser.add_argument("--iterations", type=int, nargs="*", default=[],
                        help="Iteration-count checkpoints on the real grids, e.g. 10 100 1000 10000.")
    parser.add_argument("--results-json", type=str, default=None)
    parser.add_argument("--plot", type=str, default=None)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
