from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.table_town_api import router as table_town_router

app = FastAPI(title="Create a distributed SQL query coordinator featuring vectorized SIMD execution over partitioned Parquet datasets.")
app.middleware("http")(require_route_guard)
app.include_router(table_town_router)

# Frontend pages are built from src/frontend/ and served as static assets.
