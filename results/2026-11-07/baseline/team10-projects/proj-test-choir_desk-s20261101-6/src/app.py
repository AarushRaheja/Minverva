from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.singer_api import router as singer_router
from src.network.concert_api import router as concert_router

app = FastAPI(title="choir manager")
app.middleware("http")(require_route_guard)
app.include_router(singer_router)
app.include_router(concert_router)

# Frontend pages are built from src/frontend/ and served as static assets.
