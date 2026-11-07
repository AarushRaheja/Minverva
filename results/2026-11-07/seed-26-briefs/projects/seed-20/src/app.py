from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.policy_api import router as policy_router

app = FastAPI(title="Web Application Firewall")
app.middleware("http")(require_route_guard)
app.include_router(policy_router)

# Frontend pages are built from src/frontend/ and served as static assets.
