from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.order_book_api import router as order_book_router

app = FastAPI(title="construct a ultra-low-latency financial matching engine handling FIX protocol order books with sub-microsecond execution")
app.middleware("http")(require_route_guard)
app.include_router(order_book_router)

# Frontend pages are built from src/frontend/ and served as static assets.
