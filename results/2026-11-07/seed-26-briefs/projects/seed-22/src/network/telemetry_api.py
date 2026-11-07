# src/network/telemetry_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["telemetry"])


@router.get("/api/telemetry")
async def list_telemetry(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM telemetry ORDER BY id DESC")


@router.post("/api/telemetry")
async def create_telemetry(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow("INSERT INTO telemetry (owner_id, title) VALUES ($1, $2) RETURNING *", user["id"], payload.get("title"),)


@router.get("/api/telemetry/{item_id}")
async def get_telemetry(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM telemetry WHERE id = $1", item_id)
