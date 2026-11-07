# src/network/wall_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["wall"])


@router.get("/api/walls")
async def list_walls(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM wall ORDER BY id DESC")


@router.post("/api/walls")
async def create_wall(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO wall (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/walls/{item_id}")
async def get_wall(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM wall WHERE id = $1", item_id)
