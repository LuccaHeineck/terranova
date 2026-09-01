from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import state
from api.routers import health, simulations
from ingestion.dem import build_elevation_matrix, get_geographic_bounds
from ingestion.landcover import build_roughness_matrix


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.Z = build_elevation_matrix()
    state.N = build_roughness_matrix()
    state.BOUNDS = get_geographic_bounds()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
app.include_router(simulations.router)
