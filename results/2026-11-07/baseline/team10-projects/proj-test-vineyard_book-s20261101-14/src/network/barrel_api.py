# src/network/barrel_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["barrel"])


@router.get("/api/barrels")
async def list_barrels(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM barrel ORDER BY id DESC")


@router.post("/api/barrels")
async def create_barrel(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO barrel (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/barrels/{item_id}")
async def get_barrel(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM barrel WHERE id = $1", item_id)
