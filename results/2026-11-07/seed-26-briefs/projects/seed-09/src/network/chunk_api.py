# src/network/chunk_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["chunk"])


@router.get("/api/chunks")
async def list_chunks(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM chunk ORDER BY id DESC")


@router.post("/api/chunks")
async def create_chunk(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO chunk (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/chunks/{item_id}")
async def get_chunk(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM chunk WHERE id = $1", item_id)
