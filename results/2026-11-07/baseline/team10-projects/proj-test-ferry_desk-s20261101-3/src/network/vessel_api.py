# src/network/vessel_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["vessel"])


@router.get("/api/vessels")
async def list_vessels(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM vessel ORDER BY id DESC")


@router.post("/api/vessels")
async def create_vessel(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO vessel (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/vessels/{item_id}")
async def get_vessel(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM vessel WHERE id = $1", item_id)
