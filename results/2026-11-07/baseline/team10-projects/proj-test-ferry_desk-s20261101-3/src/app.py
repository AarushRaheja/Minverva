from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.harbor_api import router as harbor_router
from src.network.sailing_api import router as sailing_router
from src.network.vessel_api import router as vessel_router

app = FastAPI(title="ferry booking desk")
app.middleware("http")(require_route_guard)
app.include_router(harbor_router)
app.include_router(sailing_router)
app.include_router(vessel_router)

# Frontend pages are built from src/frontend/ and served as static assets.
