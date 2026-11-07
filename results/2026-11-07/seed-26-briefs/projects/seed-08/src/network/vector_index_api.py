# src/network/vector_index_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["vector_index"])


@router.get("/api/vector_indexes")
async def list_vector_indices(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM vector_index ORDER BY id DESC")


@router.post("/api/vector_indexes")
async def create_vector_index(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO vector_index (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/vector_indexes/{item_id}")
async def get_vector_index(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM vector_index WHERE id = $1", item_id)
