from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.vulnerability_report_api import router as vulnerability_report_router
from src.network.container_layer_api import router as container_layer_router

app = FastAPI(title="automated vulnerability scanner")
app.middleware("http")(require_route_guard)
app.include_router(vulnerability_report_router)
app.include_router(container_layer_router)

# Frontend pages are built from src/frontend/ and served as static assets.
