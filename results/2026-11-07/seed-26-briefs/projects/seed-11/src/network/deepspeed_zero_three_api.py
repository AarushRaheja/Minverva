# src/network/deepspeed_zero_three_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["deepspeed_zero_three"])


@router.get("/api/deepspeed_zero_threes")
async def list_deepspeed_zero_threes(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM deepspeed_zero_three ORDER BY id DESC")


@router.post("/api/deepspeed_zero_threes")
async def create_deepspeed_zero_triple(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO deepspeed_zero_three (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/deepspeed_zero_threes/{item_id}")
async def get_deepspeed_zero_triple(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM deepspeed_zero_three WHERE id = $1", item_id)
