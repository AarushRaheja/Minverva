from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.buffer_api import router as buffer_router
from src.network.vst3_plugin_api import router as vst3_plugin_router

app = FastAPI(title="real-time audio dsp framework")
app.middleware("http")(require_route_guard)
app.include_router(buffer_router)
app.include_router(vst3_plugin_router)

# Frontend pages are built from src/frontend/ and served as static assets.
