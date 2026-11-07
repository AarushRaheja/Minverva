# src/network/ring_buffer_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["ring_buffer"])


@router.get("/api/ring_buffers")
async def list_ring_buffers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM ring_buffer ORDER BY id DESC")


@router.post("/api/ring_buffers")
async def create_ring_buffer(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO ring_buffer (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/ring_buffers/{item_id}")
async def get_ring_buffer(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM ring_buffer WHERE id = $1", item_id)
