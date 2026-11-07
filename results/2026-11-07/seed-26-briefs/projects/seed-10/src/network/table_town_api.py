# src/network/table_town_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["table_town"])


@router.get("/api/table_towns")
async def list_tables(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM table_town ORDER BY id DESC")


@router.post("/api/table_towns")
async def create_table(user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO table_town (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], user["title"],
    )


@router.get("/api/table_towns/{item_id}")
async def get_table(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM table_town WHERE id = $1", item_id)
