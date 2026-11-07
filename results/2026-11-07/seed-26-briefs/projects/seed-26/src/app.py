from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.video_api import router as video_router
from src.network.input_prediction_api import router as input_prediction_router

app = FastAPI(title="cloud gaming frame-streaming server")
app.middleware("http")(require_route_guard)
app.include_router(video_router)
app.include_router(input_prediction_router)

# Frontend pages are built from src/frontend/ and served as static assets.
