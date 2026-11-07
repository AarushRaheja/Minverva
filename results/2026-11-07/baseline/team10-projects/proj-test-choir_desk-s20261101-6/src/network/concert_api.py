# src/network/concert_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["concert"])


@router.get("/api/concerts")
async def list_concerts(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM concert ORDER BY id DESC")


@router.post("/api/concerts")
async def create_concert(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO concert (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/concerts/{item_id}")
async def get_concert(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM concert WHERE id = $1", item_id)
