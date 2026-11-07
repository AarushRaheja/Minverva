# src/network/vintage_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["vintage"])


@router.get("/api/vintages")
async def list_vintages(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM vintage ORDER BY id DESC")


@router.post("/api/vintages")
async def create_vintage(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO vintage (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/vintages/{item_id}")
async def get_vintage(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM vintage WHERE id = $1", item_id)
