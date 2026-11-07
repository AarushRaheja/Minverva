# src/network/cellar_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["celar"])


@router.get("/api/cellars")
async def list_cellars(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM cellar ORDER BY id DESC")


@router.post("/api/cellars")
async def create_cellar(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO cellar (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/cellars/{item_id}")
async def get_cellar(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM cellar WHERE id = $1", item_id)
