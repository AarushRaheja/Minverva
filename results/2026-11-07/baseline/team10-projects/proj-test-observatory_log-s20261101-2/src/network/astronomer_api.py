# src/network/astronomer_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["astronomer"])


@router.get("/api/astronomers")
async def list_astronomers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM astronomer ORDER BY id DESC")


@router.post("/api/astronomers")
async def create_astronomer(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO astronomer (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/astronomers/{item_id}")
async def get_astronomer(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM astronomer WHERE id = $1", item_id)
