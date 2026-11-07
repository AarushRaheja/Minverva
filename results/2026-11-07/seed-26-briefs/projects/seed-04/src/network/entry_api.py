# src/network/entry_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["entry"])


@router.get("/api/entrys")
async def list_entries(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM entry ORDER BY id DESC")


@router.post("/api/entrys")
async def create_entry(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO entry (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/entrys/{item_id}")
async def get_entry(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM entry WHERE id = $1", item_id)
