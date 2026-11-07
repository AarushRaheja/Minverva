# src/network/harbor_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["harbor"])


@router.get("/api/harbors")
async def list_harbors(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM harbor ORDER BY id DESC")


@router.post("/api/harbors")
async def create_harbor(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO harbor (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/harbors/{item_id}")
async def get_harbor(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM harbor WHERE id = $1", item_id)
