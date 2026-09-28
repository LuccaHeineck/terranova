from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import state
from api.routers import health, simulations
from config import settings
from config.settings import CORS_ALLOWED_ORIGINS, HYDROGRAPH_INFLOW_EDGE, HYDROGRAPH_OUTLET_EDGE
from ingestion.dem import build_elevation_matrix, get_geographic_bounds
from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask, find_boundary_outlet
from ingestion.landcover import build_roughness_matrix


def _load_grid(dem_path: Path, landcover_path: Path, resolution: float) -> state.Grid:
    Z = build_elevation_matrix(processed_path=dem_path, resolution=resolution)
    N = build_roughness_matrix(reference_path=dem_path, processed_path=landcover_path)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, HYDROGRAPH_OUTLET_EDGE)
    return state.Grid(
        Z=Z,
        N=N,
        dx=resolution,
        bounds=get_geographic_bounds(dem_path),
        inflow_mask=find_boundary_inflow_mask(Z, HYDROGRAPH_INFLOW_EDGE),
        boundary_elevation=boundary_elevation,
        boundary_roughness=boundary_roughness,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Both grids derive from the same raw DEM/land-cover files, so if the live
    # 30m grid loads the 90m one does too - no best-effort case for either.
    state.GRIDS = {
        30: _load_grid(
            settings.DEM_PROCESSED_PATH, settings.LANDCOVER_PROCESSED_PATH, settings.TARGET_RESOLUTION_METERS
        ),
        90: _load_grid(
            settings.DEM_VALIDATION_PROCESSED_PATH,
            settings.LANDCOVER_VALIDATION_PROCESSED_PATH,
            settings.VALIDATION_RESOLUTION_METERS,
        ),
    }
    # Loaded best-effort, not required for the app to start: gauge-driven and
    # fast modes are additive to the existing seeded-pool mode (see the spec's
    # "Run modes" decision), so a missing/not-yet-downloaded hydrograph file must
    # not break seeded_pool requests too. `create_simulation` rejects gauge_driven
    # and fast requests with a 503 instead if this stayed None.
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
    except Exception as exc:
        state.HYDROGRAPH = None
        print(
            f"WARNING: could not load the gauge hydrograph ({type(exc).__name__}: {exc}). "
            "Gauge-driven and fast runs will be rejected with a 503; seeded-pool runs are unaffected. "
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
