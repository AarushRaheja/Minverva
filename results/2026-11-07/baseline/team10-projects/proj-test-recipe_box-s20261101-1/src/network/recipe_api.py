# src/network/recipe_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["recipe"])


@router.get("/api/recipes")
async def list_recipes(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM recipe ORDER BY id DESC")


@router.post("/api/recipes")
async def create_recipe(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO recipe (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/recipes/{item_id}")
async def get_recipe(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM recipe WHERE id = $1", item_id)
