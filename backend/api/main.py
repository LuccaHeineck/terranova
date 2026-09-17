from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import state
from api.routers import health, simulations
from config.settings import CORS_ALLOWED_ORIGINS, HYDROGRAPH_INFLOW_EDGE
from ingestion.dem import build_elevation_matrix, get_geographic_bounds
from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask
from ingestion.landcover import build_roughness_matrix


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.Z = build_elevation_matrix()
    state.N = build_roughness_matrix()
    state.BOUNDS = get_geographic_bounds()
    # Loaded best-effort, not required for the app to start: gauge-driven mode is
    # additive to the existing seeded-pool mode (see the spec's "Run modes"
    # decision), so a missing/not-yet-downloaded hydrograph file must not break
    # seeded_pool requests too. `create_simulation` below rejects gauge_driven
    # requests with a clear 4xx instead if this stayed None.
    try:
        state.HYDROGRAPH = build_hydrograph()
        state.INFLOW_MASK = find_boundary_inflow_mask(state.Z, HYDROGRAPH_INFLOW_EDGE)
    except FileNotFoundError:
        state.HYDROGRAPH = None
        state.INFLOW_MASK = None
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(simulations.router)
