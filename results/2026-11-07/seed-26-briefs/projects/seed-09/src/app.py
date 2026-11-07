from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.chunk_api import router as chunk_router
from src.network.node_repair_api import router as node_repair_router

app = FastAPI(title="object storage engine")
app.middleware("http")(require_route_guard)
app.include_router(chunk_router)
app.include_router(node_repair_router)

# Frontend pages are built from src/frontend/ and served as static assets.
