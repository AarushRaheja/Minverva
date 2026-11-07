# src/network/event_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["event"])


@router.get("/api/events")
async def list_events(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM event ORDER BY id DESC")


@router.post("/api/events")
async def create_event(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO event (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/events/{item_id}")
async def get_event(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM event WHERE id = $1", item_id)
