from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.agent_api import router as agent_router
from src.network.escalation_api import router as escalation_router

app = FastAPI(title="support ticket desk")
app.middleware("http")(require_route_guard)
app.include_router(agent_router)
app.include_router(escalation_router)

# Frontend pages are built from src/frontend/ and served as static assets.
