from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import state
from api.routers import health, simulations
from config.settings import CORS_ALLOWED_ORIGINS, HYDROGRAPH_INFLOW_EDGE, HYDROGRAPH_OUTLET_EDGE
from ingestion.dem import build_elevation_matrix, get_geographic_bounds
from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask, find_boundary_outlet
from ingestion.landcover import build_roughness_matrix


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.Z = build_elevation_matrix()
    state.N = build_roughness_matrix()
    state.BOUNDS = get_geographic_bounds()
    # Only depends on the real terrain (already loaded above), not the
    # hydrograph file - unlike HYDROGRAPH/INFLOW_MASK below, there's no
    # missing-file case to handle best-effort for this.
    state.BOUNDARY_ELEVATION, state.BOUNDARY_ROUGHNESS = find_boundary_outlet(
        state.Z, state.N, HYDROGRAPH_OUTLET_EDGE
    )
    # Loaded best-effort, not required for the app to start: gauge-driven mode is
    # additive to the existing seeded-pool mode (see the spec's "Run modes"
    # decision), so a missing/not-yet-downloaded hydrograph file must not break
    # seeded_pool requests too. `create_simulation` below rejects gauge_driven
    # requests with a clear 4xx instead if this stayed None.
    #
    # Deliberately catching `Exception`, not just `FileNotFoundError`: a
    # re-download can fail in several other ways that are just as much "no usable
    # hydrograph" and just as much not a reason to take the whole app down - a
    # truncated/malformed XML body (ElementTree.ParseError), a response with no
    # `<DocumentElement>` (StopIteration), an empty row set (IndexError), or too
    # few real Vazao pairs to build a rating curve (ValueError). The warning below
    # is what surfaces the cause; the app still starts.
    try:
        state.HYDROGRAPH = build_hydrograph()
        state.INFLOW_MASK = find_boundary_inflow_mask(state.Z, HYDROGRAPH_INFLOW_EDGE)
    except Exception as exc:
        state.HYDROGRAPH = None
        state.INFLOW_MASK = None
        print(
            f"WARNING: could not load the gauge hydrograph ({type(exc).__name__}: {exc}). "
            "Gauge-driven runs will be rejected with a 503; seeded-pool runs are unaffected. "
            "Re-run scripts/download_hydrograph.py and restart to fix."
        )
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
