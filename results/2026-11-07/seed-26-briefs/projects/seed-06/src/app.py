from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.cep_task_api import router as cep_task_router
from src.network.partition_definition_api import router as partition_definition_router

app = FastAPI(title="real-time stream processing engine")
app.middleware("http")(require_route_guard)
app.include_router(cep_task_router)
app.include_router(partition_definition_router)

# Frontend pages are built from src/frontend/ and served as static assets.
