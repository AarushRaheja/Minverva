# src/network/vine_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["vine"])


@router.get("/api/vines")
async def list_vines(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM vine ORDER BY id DESC")


@router.post("/api/vines")
async def create_vine(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO vine (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/vines/{item_id}")
async def get_vine(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM vine WHERE id = $1", item_id)
