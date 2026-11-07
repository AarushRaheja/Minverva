# src/network/dough_mix_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["dough_mix"])


@router.get("/api/dough_mixes")
async def list_dough_mixes(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM dough_mix ORDER BY id DESC")


@router.post("/api/dough_mixes")
async def create_dough_mix(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO dough_mix (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/dough_mixes/{item_id}")
async def get_dough_mix(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM dough_mix WHERE id = $1", item_id)
