from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.event_invoice_api import router as event_invoice_router
from src.network.transaction_api import router as transaction_router

app = FastAPI(title="event-driven usage-based billing platform with sliding-window metering and dynamic invoice generation")
app.middleware("http")(require_route_guard)
app.include_router(event_invoice_router)
app.include_router(transaction_router)

# Frontend pages are built from src/frontend/ and served as static assets.
