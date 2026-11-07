from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.nvme_device_api import router as nvme_device_router
from src.network.thermal_profile_api import router as thermal_profile_router

app = FastAPI(title="custom PCIe NVMe controller driver")
app.middleware("http")(require_route_guard)
app.include_router(nvme_device_router)
app.include_router(thermal_profile_router)

# Frontend pages are built from src/frontend/ and served as static assets.
