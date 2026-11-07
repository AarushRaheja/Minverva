from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.state_checkpoint_api import router as state_checkpoint_router
from src.network.tool_sandbox_api import router as tool_sandbox_router

app = FastAPI(title="autonomous AI agent sandbox environment")
app.middleware("http")(require_route_guard)
app.include_router(state_checkpoint_router)
app.include_router(tool_sandbox_router)

# Frontend pages are built from src/frontend/ and served as static assets.
