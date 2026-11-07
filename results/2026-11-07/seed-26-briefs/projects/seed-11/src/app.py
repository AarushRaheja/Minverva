from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.pipeline_api import router as pipeline_router
from src.network.deepspeed_zero_three_api import router as deepspeed_zero_three_router

app = FastAPI(title="distributed LLM training orchestrator")
app.middleware("http")(require_route_guard)
app.include_router(pipeline_router)
app.include_router(deepspeed_zero_three_router)

# Frontend pages are built from src/frontend/ and served as static assets.
