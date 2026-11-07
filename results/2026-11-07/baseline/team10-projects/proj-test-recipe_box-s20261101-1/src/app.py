from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.recipe_api import router as recipe_router
from src.network.pantry_item_api import router as pantry_item_router
from src.network.cook_api import router as cook_router

app = FastAPI(title="recipe box")
app.middleware("http")(require_route_guard)
app.include_router(recipe_router)
app.include_router(pantry_item_router)
app.include_router(cook_router)

# Frontend pages are built from src/frontend/ and served as static assets.
