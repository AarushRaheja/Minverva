# src/network/escalation_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["escalation"])


@router.get("/api/escalations")
async def list_escalations(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM escalation ORDER BY id DESC")


@router.post("/api/escalations")
async def create_escalation(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO escalation (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/escalations/{item_id}")
async def get_escalation(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM escalation WHERE id = $1", item_id)
