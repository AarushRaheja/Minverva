# src/network/state_checkpoint_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["state_checkpoint"])


@router.get("/api/state_checkpoints")
async def list_state_checkpoints(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM state_checkpoint ORDER BY id DESC")


@router.post("/api/state_checkpoints")
async def create_state_checkpoint(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO state_checkpoint (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/state_checkpoints/{item_id}")
async def get_state_checkpoint(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM state_checkpoint WHERE id = $1", item_id)
