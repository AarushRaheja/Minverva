from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.domain_api import router as domain_router

app = FastAPI(title="global CDN edge worker runtime")
app.middleware("http")(require_route_guard)
app.include_router(domain_router)

# Frontend pages are built from src/frontend/ and served as static assets.
