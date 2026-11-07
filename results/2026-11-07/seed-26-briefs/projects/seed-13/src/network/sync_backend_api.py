# src/network/sync_backend_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["sync_backend"])


@router.get("/api/sync_backends")
async def list_sync_backends(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM sync_backend ORDER BY id DESC")


@router.post("/api/sync_backends")
async def create_sync_backend(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO sync_backend (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/sync_backends/{item_id}")
async def get_sync_backend(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM sync_backend WHERE id = $1", item_id)
