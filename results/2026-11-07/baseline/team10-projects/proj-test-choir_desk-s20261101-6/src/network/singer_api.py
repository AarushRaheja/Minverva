# src/network/singer_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["singer"])


@router.get("/api/singers")
async def list_singers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM singer ORDER BY id DESC")


@router.post("/api/singers")
async def create_singer(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO singer (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/singers/{item_id}")
async def get_singer(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM singer WHERE id = $1", item_id)
