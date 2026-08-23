from fastapi import FastAPI

from api.routers import health

app = FastAPI()
app.include_router(health.router)
