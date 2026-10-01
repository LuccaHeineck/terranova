"""REST + WebSocket routes for running the CA flood simulation.

Serves the real Lajeado/Estrela grid only (loaded once at startup, see
`api/state.py`) - no synthetic-grid option here, since `api/` may only depend
on `config/`, `ingestion/`, `simulation/`, `validation/` per
`docs/ARCHITECTURE.md` (never `examples/`, which nothing else imports), and by
this roadmap step there's already a real, ingested dataset worth serving. Three
resolutions of it: the live 30m grid (default), an unvalidated 60m grid
(`resolution=60`) and the 90m validation grid (`resolution=90`).

A run is created via `POST /simulations` (validated parameters, no simulation
work happens yet) and consumed exactly once via
`WS /simulations/{run_id}/stream`. Three modes:

- `"seeded_pool"` - closed system, a single water pool of `seed_volume`
  (default 400, the step-5 constant) seeded at the terrain's lowest point, or at
  an optional WGS84 `seed_location` placed on the grid through its real
  projected transform (`ingestion.dem.lonlat_to_cell`).
- `"gauge_driven"` - open system, driven by the real May 2024 gauge hydrograph
  via `simulation.engine`'s `inflow`/`compute_stable_dt` (roadmap step 9),
  optionally stopping at the observed peak (`stop_at_peak`).
- `"fast"` - the non-temporal, Torres-inspired `simulation.fast_engine`
  (docs/tcc-deviations.md sections 19 and 23) at the same hydrograph's steady peak
  discharge. It has no time steps, so its stream is exactly one frame
  (`step: 0`) followed by `done` - the same contract as the temporal modes,
  degenerate rather than different (section 21 explains why this isn't a
  separate REST endpoint).

There's no persistence layer for this project (see docs/project-plan.md), so a
pending run only exists in an in-memory dict between those two calls.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator
from starlette.websockets import WebSocketState

from api.state import Grid, get_grids, get_hydrograph
from ingestion.dem import grid_footprint, lonlat_to_cell
from ingestion.hydrograph import Hydrograph, discharge_to_inflow
from simulation.engine import (
    DEFAULT_OUTFLOW_FRACTION,
    VON_NEUMANN_MAX_OUTFLOW_FRACTION,
    compute_stable_dt,
    outflow_fraction_for_dt,
    seed_pool_at,
    seed_pool_at_lowest_point,
    step,
)
from simulation.fast_engine import classify_steady_flood

router = APIRouter()

# Seeded-pool volume, in the frames' own `volume` unit: summed cell depth (m).
# The default, the step-5 constant, fills the 5x5 seed patch 16 m deep; the cap
# fills it 400 m deep - past that it's no longer a pool worth simulating.
DEFAULT_SEED_VOLUME = 400.0
MAX_SEED_VOLUME = 10_000.0

# Wet-cell cutoff for the fast engine's `flooded` mask - the same value
# examples/validate_may2024.py and examples/fast_mode_may2024.py threshold both
# engines' extents with.
FLOODED_DEPTH_THRESHOLD_M = 0.01

# Parameters that only mean something for a time-stepped run.
_TEMPORAL_ONLY_FIELDS = ("steps", "frame_interval", "outflow_fraction", "stop_at_peak", "neighborhood")
# Parameters that only mean something for a seeded-pool run - the other two
# modes are driven by the gauge hydrograph, not by an initial pool.
_SEEDED_POOL_ONLY_FIELDS = ("seed_volume", "seed_location")


class SeedLocation(BaseModel):
    """A WGS84 point; converted to a grid cell server-side, where the grid's real CRS is known."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class SimulationParams(BaseModel):
    mode: Literal["seeded_pool", "gauge_driven", "fast"] = "seeded_pool"
    resolution: Literal[30, 60, 90] = 30
    steps: int | None = Field(default=None, gt=0)
    frame_interval: int | None = Field(default=None, gt=0)
    outflow_fraction: float = Field(default=DEFAULT_OUTFLOW_FRACTION, gt=0, le=1)
    stop_at_peak: bool = False
    # The temporal engine's neighborhood. Moore is the TCC's model and the only validated one
    # (docs/tcc-deviations.md sections 16.4 and 22); von Neumann is an unvalidated 4-neighbor option. The
    # fast engine is Moore-only, so - like the other temporal-only fields - this is rejected for mode "fast".
    neighborhood: Literal["moore", "von_neumann"] = "moore"
    seed_volume: float = Field(default=DEFAULT_SEED_VOLUME, gt=0, le=MAX_SEED_VOLUME)
    # None: seed at the terrain's lowest point, as before this parameter existed.
    seed_location: SeedLocation | None = None

    @model_validator(mode="after")
    def _validate_fields_match_mode(self) -> "SimulationParams":
        if self.mode != "seeded_pool":
            given = [name for name in _SEEDED_POOL_ONLY_FIELDS if name in self.model_fields_set]
            if given:
                raise ValueError(f"{', '.join(given)} only applies when mode is 'seeded_pool'")
        if self.mode == "fast":
            given = [name for name in _TEMPORAL_ONLY_FIELDS if name in self.model_fields_set]
            if given:
                raise ValueError(
                    f"{', '.join(given)} must not be given when mode is 'fast' - it has no time steps"
                )
            return self
        if self.frame_interval is None:
            raise ValueError(f"frame_interval is required when mode is '{self.mode}'")
        if self.neighborhood == "von_neumann" and self.outflow_fraction > VON_NEUMANN_MAX_OUTFLOW_FRACTION:
            raise ValueError(
                f"outflow_fraction must be <= {VON_NEUMANN_MAX_OUTFLOW_FRACTION} with the von Neumann neighborhood - "
                "above it its result depends on the substep fraction (docs/tcc-deviations.md section 22)"
            )
        if self.mode == "seeded_pool" and self.steps is None:
            raise ValueError("steps is required when mode is 'seeded_pool'")
        if self.mode == "seeded_pool" and self.stop_at_peak:
            raise ValueError("stop_at_peak only applies when mode is 'gauge_driven'")
        if self.mode == "gauge_driven" and self.steps is not None:
            raise ValueError(
                "steps must not be given when mode is 'gauge_driven' - the gauge "
                "hydrograph's own duration determines run length"
            )
        return self


class Bounds(BaseModel):
    west: float
    south: float
    east: float
    north: float


class SimulationCreated(BaseModel):
    run_id: str
    grid_shape: tuple[int, int]
    bounds: Bounds
    # seeded_pool only: the (row, col) the pool is centered on - the cell under
    # seed_location, or the lowest-point default's own center. None otherwise.
    seed_cell: tuple[int, int] | None = None


class GridInfo(BaseModel):
    resolution: int
    grid_shape: tuple[int, int]
    bounds: Bounds
    # The grid's true outline as four WGS84 (lat, lon) corners, clockwise from the
    # top-left. `bounds` is its axis-aligned envelope, which also covers thin
    # slivers outside the (UTM north-up, so slightly rotated) grid.
    footprint: list[tuple[float, float]]


@dataclass
class _PendingRun:
    params: SimulationParams
    # seeded_pool with a seed_location only; None seeds at the lowest point.
    seed_cell: tuple[int, int] | None


_pending_runs: dict[str, _PendingRun] = {}


def _bounds(grid: Grid) -> Bounds:
    west, south, east, north = grid.bounds
    return Bounds(west=west, south=south, east=east, north=north)


def _lowest_point_seed_cell(Z: np.ndarray) -> tuple[int, int]:
    """The center `seed_pool_at_lowest_point` uses (same clipping), for reporting it."""
    ry, rx = np.unravel_index(np.argmin(Z), Z.shape)
    return int(np.clip(ry, 2, Z.shape[0] - 3)), int(np.clip(rx, 2, Z.shape[1] - 3))


@router.get("/grids", response_model=list[GridInfo])
def list_grids(grids: dict[int, Grid] = Depends(get_grids)) -> list[GridInfo]:
    """The served grids, so a client can place things on them (e.g. a seed location) before any run."""
    return [
        GridInfo(
            resolution=resolution,
            grid_shape=grid.Z.shape,
            bounds=_bounds(grid),
            footprint=grid_footprint(grid.crs, grid.transform, grid.Z.shape),
        )
        for resolution, grid in sorted(grids.items())
    ]


@router.post("/simulations", response_model=SimulationCreated)
def create_simulation(
    params: SimulationParams,
    grids: dict[int, Grid] = Depends(get_grids),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
) -> SimulationCreated:
    if params.mode in ("gauge_driven", "fast") and hydrograph is None:
        raise HTTPException(
            status_code=503,
            detail=f"{params.mode} mode needs the gauge hydrograph, which isn't loaded - "
            "run scripts/download_hydrograph.py and restart the API",
        )

    grid = grids[params.resolution]
    seed_cell = None
    if params.seed_location is not None:
        location = params.seed_location
        seed_cell = lonlat_to_cell(location.lon, location.lat, grid.crs, grid.transform, grid.Z.shape)
        if seed_cell is None:
            raise HTTPException(
                status_code=422,
                detail=f"seed_location ({location.lat}, {location.lon}) is outside the "
                f"{params.resolution} m grid",
            )

    run_id = str(uuid.uuid4())
    _pending_runs[run_id] = _PendingRun(params=params, seed_cell=seed_cell)
    reported_seed_cell = None
    if params.mode == "seeded_pool":
        reported_seed_cell = seed_cell if seed_cell is not None else _lowest_point_seed_cell(grid.Z)
    return SimulationCreated(
        run_id=run_id,
        grid_shape=grid.Z.shape,
        bounds=_bounds(grid),
        seed_cell=reported_seed_cell,
    )


async def _yield_or_stop(client_gone: asyncio.Event) -> None:
    """Called once per temporal engine step. Yields to the event loop, so other
    requests (e.g. starting a fast run) are served while a long run computes
    rather than only between frames, and ends the run within one step once the
    client has disconnected, rather than at its next frame send."""
    await asyncio.sleep(0)
    if client_gone.is_set():
        raise WebSocketDisconnect(code=1000)


async def _run_seeded_pool(
    websocket: WebSocket,
    params: SimulationParams,
    grid: Grid,
    seed_cell: tuple[int, int] | None,
    client_gone: asyncio.Event,
) -> None:
    Z, N = grid.Z, grid.N
    H = np.zeros_like(Z)
    if seed_cell is None:
        seed_pool_at_lowest_point(Z, H, params.seed_volume)
    else:
        seed_pool_at(H, params.seed_volume, *seed_cell)
    seed_volume = params.seed_volume

    for t in range(1, params.steps + 1):
        await _yield_or_stop(client_gone)
        H = step(Z, H, N, outflow_fraction=params.outflow_fraction, neighborhood=params.neighborhood)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        # Closed system: the total is the requested seed volume at every step.
        # Relative, like _run_gauge_driven's, since seed_volume now ranges up to
        # MAX_SEED_VOLUME (4e-7 at the default 400, tighter than the old 1e-6).
        assert abs(H.sum() - seed_volume) <= 1e-9 * max(1.0, seed_volume), (
            f"volume drifted at step {t}: {H.sum()} vs {seed_volume}"
        )
        if t % params.frame_interval == 0 or t == params.steps:
            await websocket.send_json({"step": t, "depth": H.tolist(), "volume": float(H.sum())})


async def _run_gauge_driven(
    websocket: WebSocket,
    params: SimulationParams,
    grid: Grid,
    hydrograph: Hydrograph,
    client_gone: asyncio.Event,
) -> None:
    Z, N = grid.Z, grid.N
    H = np.zeros_like(Z)
    cell_area_m2 = grid.dx ** 2
    # The observed peak is where examples/validate_may2024.py stops too - the
    # moment the fast mode's steady forcing represents, and the one the real
    # SGB flood extent was mapped at.
    end_time = hydrograph.peak_elapsed_seconds if params.stop_at_peak else hydrograph.duration_seconds
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    while elapsed_time < end_time:
        await _yield_or_stop(client_gone)
        # dt_cfl is the raw CFL bound (courant_number=1.0), kept separate from the
        # capped dt below so outflow_fraction_for_dt can tell how much smaller an
        # application-level cap made this step's dt than physics alone would allow.
        dt_cfl = compute_stable_dt(Z, H, N, grid.dx, neighborhood=params.neighborhood)
        # Cap at the raw ANA feed's own typical sample spacing (~900s). CFL gives
        # an upper bound on dt, not a target, so a smaller dt is always safe - and
        # on a still-dry grid `compute_stable_dt` returns engine.py's
        # `_NO_FLOW_FALLBACK_DT_SECONDS` (3600s), which is sized for redistribution
        # stability, not for how much external inflow volume one step should
        # inject. Without this cap the first step dumps an hour of real
        # thousands-of-m3/s discharge into a few boundary cells at once. Capping
        # bounds any single injection burst to a physically motivated timescale
        # instead of an arbitrary hour (it does not eliminate the first-step
        # transient - concentrating a whole river's discharge through a few 30m
        # cells is an inherent coarse-grid simplification).
        dt = min(dt_cfl, 900.0)
        # Clip so the final iteration lands exactly on end_time, never past it -
        # Hydrograph.discharge_at raises outside its recorded range.
        dt = min(dt, end_time - elapsed_time)

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, grid.inflow_mask, cell_area_m2)

        volume_before = H.sum()
        H = step(
            Z,
            H,
            N,
            # Scaled down whenever an application-level cap (above) makes dt
            # smaller than the raw CFL bound would allow - see
            # outflow_fraction_for_dt's docstring in simulation/engine.py for why.
            outflow_fraction=outflow_fraction_for_dt(params.outflow_fraction, dt, dt_cfl),
            inflow=inflow,
            boundary_elevation=grid.boundary_elevation,
            boundary_roughness=grid.boundary_roughness,
            neighborhood=params.neighborhood,
        )
        # step()'s return value already reflects whatever left through the
        # outlet boundary - this is the exact bookkeeping invariant documented
        # in step()'s own docstring, not an approximation. Roadmap step 10: the
        # outlet exists so a real multi-day event doesn't flood the entire
        # closed ROI to physically implausible depths (see docs/tcc-deviations.md).
        cumulative_outflow += volume_before + inflow.sum() - H.sum()
        elapsed_time += dt
        cumulative_inflow += inflow.sum()
        t += 1

        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        # Relative (as in _run_seeded_pool): the volume grows to order 1e7 over
        # 100k+ steps of real inflow, where float64 round-off alone can exceed an
        # absolute 1e-6 without anything actually being wrong.
        expected_volume = cumulative_inflow - cumulative_outflow
        assert abs(H.sum() - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), (
            f"volume drifted at step {t}: {H.sum()} vs {expected_volume}"
        )

        if t % params.frame_interval == 0 or elapsed_time >= end_time:
            await websocket.send_json(
                {
                    "step": t,
                    "depth": H.tolist(),
                    "volume": float(H.sum()),
                    "elapsed_time": elapsed_time,
                    "cumulative_inflow": float(cumulative_inflow),
                    "cumulative_outflow": float(cumulative_outflow),
                }
            )


async def _run_fast(websocket: WebSocket, grid: Grid, hydrograph: Hydrograph) -> None:
    start = time.perf_counter()
    # Off the event loop: both of classify_steady_flood's passes are plain
    # Python loops (~1s on the 30m grid), unlike the temporal modes' per-step
    # NumPy calls, which at least yield between frames.
    result = await asyncio.to_thread(
        classify_steady_flood,
        grid.Z,
        grid.N,
        grid.dx,
        hydrograph.peak_discharge_m3s,
        grid.inflow_mask,
        boundary_elevation=grid.boundary_elevation,
        boundary_roughness=grid.boundary_roughness,
        depth_threshold_m=FLOODED_DEPTH_THRESHOLD_M,
    )
    compute_seconds = time.perf_counter() - start

    # Discharge continuity - this engine's analogue of the temporal modes'
    # mass-balance assertions (same check as examples/fast_mode_may2024.py).
    balance = result.outflow_m3s + result.retained_m3s
    assert abs(balance - result.inflow_m3s) <= 1e-9 * max(1.0, result.inflow_m3s), (
        f"discharge continuity violated: in={result.inflow_m3s}, out+retained={balance}"
    )

    await websocket.send_json(
        {
            # No time integration: step 0 and no elapsed_time. `volume` is the
            # steady water depth summed over cells, the same unit as the
            # temporal frames' `volume`, not a conserved quantity here.
            "step": 0,
            "depth": result.depth.tolist(),
            "volume": float(result.depth.sum()),
            "peak_discharge_m3s": result.inflow_m3s,
            "peak_elapsed_time": hydrograph.peak_elapsed_seconds,
            "outflow_m3s": result.outflow_m3s,
            "retained_m3s": result.retained_m3s,
            "flooded_cells": int(result.flooded.sum()),
            "compute_seconds": compute_seconds,
        }
    )


@router.websocket("/simulations/{run_id}/stream")
async def stream_simulation(
    websocket: WebSocket,
    run_id: str,
    grids: dict[int, Grid] = Depends(get_grids),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
) -> None:
    # Popped rather than just read: a run can only be streamed once, matching
    # the "no persistence layer" decision - reconnecting with the same run_id
    # isn't a supported resume mechanism.
    pending = _pending_runs.pop(run_id, None)
    if pending is None:
        await websocket.close(code=4004, reason="unknown run_id")
        return
    params = pending.params

    await websocket.accept()
    grid = grids[params.resolution]

    # The client never sends anything, so the only message receive() can
    # return is its disconnect (e.g. the frontend's Stop button).
    client_gone = asyncio.Event()

    async def _watch_for_disconnect() -> None:
        try:
            await websocket.receive()
        finally:
            client_gone.set()

    watcher = asyncio.create_task(_watch_for_disconnect())
    try:
        if params.mode == "seeded_pool":
            await _run_seeded_pool(websocket, params, grid, pending.seed_cell, client_gone)
        elif params.mode == "gauge_driven":
            await _run_gauge_driven(websocket, params, grid, hydrograph, client_gone)
        else:
            await _run_fast(websocket, grid, hydrograph)
        await websocket.send_json({"done": True})
    except WebSocketDisconnect:
        # The client left mid-run: a temporal loop noticed it via client_gone,
        # or a send_json found the socket closed. Either way the run just ends.
        pass
    finally:
        watcher.cancel()
        # Closing a socket the client already closed would raise.
        if not client_gone.is_set() and websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()
