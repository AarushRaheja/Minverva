# src/network/pantry_item_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["pantry_item"])


@router.get("/api/pantry_items")
async def list_pantry_items(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM pantry_item ORDER BY id DESC")


@router.post("/api/pantry_items")
async def create_pantry_item(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO pantry_item (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/pantry_items/{item_id}")
async def get_pantry_item(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM pantry_item WHERE id = $1", item_id)
