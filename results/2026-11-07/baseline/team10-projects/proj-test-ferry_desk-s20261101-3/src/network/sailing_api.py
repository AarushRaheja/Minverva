# src/network/sailing_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["sailing"])


@router.get("/api/sailings")
async def list_sailings(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM sailing ORDER BY id DESC")


@router.post("/api/sailings")
async def create_sailing(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO sailing (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/sailings/{item_id}")
async def get_sailing(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM sailing WHERE id = $1", item_id)
