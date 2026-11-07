# src/network/patroller_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["patroller"])


@router.get("/api/patrollers")
async def list_patrollers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM patroller ORDER BY id DESC")


@router.post("/api/patrollers")
async def create_patroller(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO patroller (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/patrollers/{item_id}")
async def get_patroller(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM patroller WHERE id = $1", item_id)
