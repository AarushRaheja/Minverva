# src/network/belay_check_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["belay_check"])


@router.get("/api/belay_checks")
async def list_belay_checks(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM belay_check ORDER BY id DESC")


@router.post("/api/belay_checks")
async def create_belay_check(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO belay_check (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/belay_checks/{item_id}")
async def get_belay_check(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM belay_check WHERE id = $1", item_id)
