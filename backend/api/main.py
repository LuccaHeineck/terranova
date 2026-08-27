from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import state
from api.routers import health, simulations
from ingestion.dem import build_elevation_matrix
from ingestion.landcover import build_roughness_matrix


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.Z = build_elevation_matrix()
    state.N = build_roughness_matrix()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
app.include_router(simulations.router)
