# src/network/baker_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["baker"])


@router.get("/api/bakers")
async def list_bakers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM baker ORDER BY id DESC")


@router.post("/api/bakers")
async def create_baker(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO baker (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/bakers/{item_id}")
async def get_baker(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM baker WHERE id = $1", item_id)
