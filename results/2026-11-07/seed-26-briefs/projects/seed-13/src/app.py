from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.feature_api import router as feature_router
from src.network.sync_backend_api import router as sync_backend_router

app = FastAPI(title="enterprise ML feature store")
app.middleware("http")(require_route_guard)
app.include_router(feature_router)
app.include_router(sync_backend_router)

# Frontend pages are built from src/frontend/ and served as static assets.
