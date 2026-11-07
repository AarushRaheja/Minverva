from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.account_provider_api import router as account_provider_router
from src.network.account_request_api import router as account_request_router

app = FastAPI(title="peer-to-peer overlay network")
app.middleware("http")(require_route_guard)
app.include_router(account_provider_router)
app.include_router(account_request_router)

# Frontend pages are built from src/frontend/ and served as static assets.
