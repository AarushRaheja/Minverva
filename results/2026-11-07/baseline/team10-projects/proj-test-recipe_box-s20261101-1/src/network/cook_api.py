# src/network/cook_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["cook"])


@router.get("/api/cooks")
async def list_cooks(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM cook ORDER BY id DESC")


@router.post("/api/cooks")
async def create_cook(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO cook (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/cooks/{item_id}")
async def get_cook(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM cook WHERE id = $1", item_id)
