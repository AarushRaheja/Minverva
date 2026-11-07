from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.device_api import router as device_router
from src.network.sensor_fusion_api import router as sensor_fusion_router

app = FastAPI(title="autonomous flight controller firmware")
app.middleware("http")(require_route_guard)
app.include_router(device_router)
app.include_router(sensor_fusion_router)

# Frontend pages are built from src/frontend/ and served as static assets.
