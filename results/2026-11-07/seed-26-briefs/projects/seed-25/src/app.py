from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.audio_track_api import router as audio_track_router

app = FastAPI(title="spatial 3D audio rendering pipeline streaming low-latency multi-user audio over WebSockets and WebRTC")
app.middleware("http")(require_route_guard)
app.include_router(audio_track_router)

# Frontend pages are built from src/frontend/ and served as static assets.
