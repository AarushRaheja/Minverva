from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.comet_api import router as comet_router
from src.network.astronomer_api import router as astronomer_router
from src.network.observation_api import router as observation_router
from src.network.telescope_api import router as telescope_router

app = FastAPI(title="observatory log")
app.middleware("http")(require_route_guard)
app.include_router(comet_router)
app.include_router(astronomer_router)
app.include_router(observation_router)
app.include_router(telescope_router)

# Frontend pages are built from src/frontend/ and served as static assets.
