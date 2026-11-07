from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.barrel_api import router as barrel_router
from src.network.vine_api import router as vine_router
from src.network.cellar_api import router as cellar_router
from src.network.vintage_api import router as vintage_router

app = FastAPI(title="vineyard ledger")
app.middleware("http")(require_route_guard)
app.include_router(barrel_router)
app.include_router(vine_router)
app.include_router(cellar_router)
app.include_router(vintage_router)

# Frontend pages are built from src/frontend/ and served as static assets.
