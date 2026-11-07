from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.bucket_api import router as bucket_router
from src.network.raft_log_api import router as raft_log_router

app = FastAPI(title="distributed transactional key-value store")
app.middleware("http")(require_route_guard)
app.include_router(bucket_router)
app.include_router(raft_log_router)

# Frontend pages are built from src/frontend/ and served as static assets.
