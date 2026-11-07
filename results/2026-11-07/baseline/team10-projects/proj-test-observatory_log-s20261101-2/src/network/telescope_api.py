# src/network/telescope_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["telescope"])


@router.get("/api/telescopes")
async def list_telescopes(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM telescope ORDER BY id DESC")


@router.post("/api/telescopes")
async def create_telescope(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO telescope (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/telescopes/{item_id}")
async def get_telescope(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM telescope WHERE id = $1", item_id)
