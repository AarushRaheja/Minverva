# src/network/manuscript_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["manuscript"])


@router.get("/api/manuscripts")
async def list_manuscripts(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM manuscript ORDER BY id DESC")


@router.post("/api/manuscripts")
async def create_manuscript(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO manuscript (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/manuscripts/{item_id}")
async def get_manuscript(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM manuscript WHERE id = $1", item_id)
