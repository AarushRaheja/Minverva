from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.wall_api import router as wall_router
from src.network.belay_check_api import router as belay_check_router

app = FastAPI(title="climbing gym app")
app.middleware("http")(require_route_guard)
app.include_router(wall_router)
app.include_router(belay_check_router)

# Frontend pages are built from src/frontend/ and served as static assets.
