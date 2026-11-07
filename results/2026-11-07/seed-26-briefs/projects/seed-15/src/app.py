from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.event_api import router as event_router
from src.network.ring_buffer_api import router as ring_buffer_router

app = FastAPI(title="high-performance asynchronous IO event loop framework for Linux utilizing zero-copy io_uring ring buffers")
app.middleware("http")(require_route_guard)
app.include_router(event_router)
app.include_router(ring_buffer_router)

# Frontend pages are built from src/frontend/ and served as static assets.
