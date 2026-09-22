"""REST + WebSocket routes for running the CA flood simulation.

Serves the real Lajeado/Estrela grid only (loaded once at startup, see
`api/state.py`) - no synthetic-grid option here, since `api/` may only depend
on `config/`, `ingestion/`, `simulation/`, `validation/` per
`docs/ARCHITECTURE.md` (never `examples/`, which nothing else imports), and by
this roadmap step there's already a real, ingested dataset worth serving.

A run is created via `POST /simulations` (validated parameters, no simulation
work happens yet) and consumed exactly once via
`WS /simulations/{run_id}/stream`. Two modes: `"seeded_pool"` (closed system, a
single water pool seeded at the terrain's lowest point - unchanged since step 5)
and `"gauge_driven"` (open system, driven by the real May 2024 gauge hydrograph
via `simulation.engine`'s `inflow`/`compute_stable_dt`, roadmap step 9). There's
no persistence layer for this project (see docs/project-plan.md), so a pending
run only exists in an in-memory dict between those two calls.
"""

import uuid
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator

from api.state import (
    get_boundary_elevation,
    get_boundary_roughness,
    get_bounds,
    get_hydrograph,
    get_inflow_mask,
    get_roughness,
    get_terrain,
)
from config.settings import TARGET_RESOLUTION_METERS
from ingestion.hydrograph import Hydrograph, discharge_to_inflow
from simulation.engine import compute_stable_dt, seed_pool_at_lowest_point, step

router = APIRouter()

SEED_VOLUME = 400.0


class SimulationParams(BaseModel):
    mode: Literal["seeded_pool", "gauge_driven"] = "seeded_pool"
    steps: int | None = Field(default=None, gt=0)
    frame_interval: int = Field(gt=0)
    outflow_fraction: float = Field(default=0.5, gt=0, le=1)

    @model_validator(mode="after")
    def _validate_steps_matches_mode(self) -> "SimulationParams":
        if self.mode == "seeded_pool" and self.steps is None:
            raise ValueError("steps is required when mode is 'seeded_pool'")
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


_pending_runs: dict[str, SimulationParams] = {}


@router.post("/simulations", response_model=SimulationCreated)
def create_simulation(
    params: SimulationParams,
    Z: np.ndarray = Depends(get_terrain),
    bounds: tuple[float, float, float, float] = Depends(get_bounds),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
) -> SimulationCreated:
    if params.mode == "gauge_driven" and hydrograph is None:
        raise HTTPException(
            status_code=503,
            detail="gauge-driven data not loaded - run scripts/download_hydrograph.py and restart the API",
        )

    run_id = str(uuid.uuid4())
    _pending_runs[run_id] = params
    west, south, east, north = bounds
    return SimulationCreated(
        run_id=run_id,
        grid_shape=Z.shape,
        bounds=Bounds(west=west, south=south, east=east, north=north),
    )


async def _run_seeded_pool(websocket: WebSocket, params: SimulationParams, Z: np.ndarray, N: np.ndarray) -> None:
    H = np.zeros_like(Z)
    seed_pool_at_lowest_point(Z, H, SEED_VOLUME)
    initial_volume = H.sum()

    for t in range(1, params.steps + 1):
        H = step(Z, H, N, outflow_fraction=params.outflow_fraction)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        if t % params.frame_interval == 0 or t == params.steps:
            await websocket.send_json({"step": t, "depth": H.tolist(), "volume": float(H.sum())})


async def _run_gauge_driven(
    websocket: WebSocket,
    params: SimulationParams,
    Z: np.ndarray,
    N: np.ndarray,
    hydrograph: Hydrograph,
    inflow_mask: np.ndarray,
    boundary_elevation: np.ndarray,
    boundary_roughness: np.ndarray,
) -> None:
    H = np.zeros_like(Z)
    cell_area_m2 = TARGET_RESOLUTION_METERS ** 2
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    cumulative_outflow = 0.0
    t = 0

    while elapsed_time < hydrograph.duration_seconds:
        dt = compute_stable_dt(Z, H, N, TARGET_RESOLUTION_METERS)
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
        dt = min(dt, 900.0)
        # Clip so the final iteration lands exactly on the hydrograph's end, never
        # past it - Hydrograph.discharge_at raises outside its recorded range.
        dt = min(dt, hydrograph.duration_seconds - elapsed_time)

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        volume_before = H.sum()
        H = step(
            Z,
            H,
            N,
            outflow_fraction=params.outflow_fraction,
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
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
        # Relative, unlike _run_seeded_pool's absolute 1e-6: there the volume is a
        # small fixed constant (SEED_VOLUME), here it grows to order 1e7 over
        # 100k+ steps of real inflow, where float64 round-off alone can exceed an
        # absolute 1e-6 without anything actually being wrong.
        expected_volume = cumulative_inflow - cumulative_outflow
        assert abs(H.sum() - expected_volume) <= 1e-9 * max(1.0, abs(expected_volume)), (
            f"volume drifted at step {t}: {H.sum()} vs {expected_volume}"
        )

        if t % params.frame_interval == 0 or elapsed_time >= hydrograph.duration_seconds:
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


@router.websocket("/simulations/{run_id}/stream")
async def stream_simulation(
    websocket: WebSocket,
    run_id: str,
    Z: np.ndarray = Depends(get_terrain),
    N: np.ndarray = Depends(get_roughness),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
    inflow_mask: np.ndarray | None = Depends(get_inflow_mask),
    boundary_elevation: np.ndarray | None = Depends(get_boundary_elevation),
    boundary_roughness: np.ndarray | None = Depends(get_boundary_roughness),
) -> None:
    # Popped rather than just read: a run can only be streamed once, matching
    # the "no persistence layer" decision - reconnecting with the same run_id
    # isn't a supported resume mechanism.
    params = _pending_runs.pop(run_id, None)
    if params is None:
        await websocket.close(code=4004, reason="unknown run_id")
        return

    await websocket.accept()

    try:
        if params.mode == "seeded_pool":
            await _run_seeded_pool(websocket, params, Z, N)
        else:
            await _run_gauge_driven(
                websocket, params, Z, N, hydrograph, inflow_mask, boundary_elevation, boundary_roughness
            )
        await websocket.send_json({"done": True})
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
