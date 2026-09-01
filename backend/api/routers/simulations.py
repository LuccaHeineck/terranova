"""REST + WebSocket routes for running the CA flood simulation.

Serves the real Lajeado/Estrela grid only (loaded once at startup, see
`api/state.py`) - no synthetic-grid option here, since `api/` may only depend
on `config/`, `ingestion/`, `simulation/`, `validation/` per
`docs/ARCHITECTURE.md` (never `examples/`, which nothing else imports), and by
this roadmap step there's already a real, ingested dataset worth serving.

A run is created via `POST /simulations` (validated parameters, no simulation
work happens yet) and consumed exactly once via
`WS /simulations/{run_id}/stream`, which runs `simulation.engine.step` in a
loop and sends a JSON frame every `frame_interval` steps. There's no
persistence layer for this project (see docs/project-plan.md), so a pending
run only exists in an in-memory dict between those two calls.
"""

import uuid

import numpy as np
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from api.state import get_bounds, get_roughness, get_terrain
from simulation.engine import seed_pool_at_lowest_point, step

router = APIRouter()

SEED_VOLUME = 400.0


class SimulationParams(BaseModel):
    steps: int = Field(gt=0)
    frame_interval: int = Field(gt=0)
    outflow_fraction: float = Field(default=0.5, gt=0, le=1)


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
) -> SimulationCreated:
    run_id = str(uuid.uuid4())
    _pending_runs[run_id] = params
    west, south, east, north = bounds
    return SimulationCreated(
        run_id=run_id,
        grid_shape=Z.shape,
        bounds=Bounds(west=west, south=south, east=east, north=north),
    )


@router.websocket("/simulations/{run_id}/stream")
async def stream_simulation(
    websocket: WebSocket,
    run_id: str,
    Z: np.ndarray = Depends(get_terrain),
    N: np.ndarray = Depends(get_roughness),
) -> None:
    # Popped rather than just read: a run can only be streamed once, matching
    # the "no persistence layer" decision - reconnecting with the same run_id
    # isn't a supported resume mechanism.
    params = _pending_runs.pop(run_id, None)
    if params is None:
        await websocket.close(code=4004, reason="unknown run_id")
        return

    await websocket.accept()

    H = np.zeros_like(Z)
    seed_pool_at_lowest_point(Z, H, SEED_VOLUME)
    initial_volume = H.sum()

    try:
        for t in range(1, params.steps + 1):
            H = step(Z, H, N, outflow_fraction=params.outflow_fraction)
            assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
            assert abs(H.sum() - initial_volume) < 1e-6, (
                f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
            )
            if t % params.frame_interval == 0 or t == params.steps:
                await websocket.send_json({"step": t, "depth": H.tolist(), "volume": float(H.sum())})
        await websocket.send_json({"done": True})
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
