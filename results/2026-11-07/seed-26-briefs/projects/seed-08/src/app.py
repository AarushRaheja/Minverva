from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.vector_index_api import router as vector_index_router
from src.network.metadata_filter_api import router as metadata_filter_router

app = FastAPI(title="high-throughput vector database")
app.middleware("http")(require_route_guard)
app.include_router(vector_index_router)
app.include_router(metadata_filter_router)

# Frontend pages are built from src/frontend/ and served as static assets.
