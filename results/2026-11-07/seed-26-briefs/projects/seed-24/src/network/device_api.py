# src/network/device_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["device"])


@router.get("/api/devices")
async def list_devices(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM device ORDER BY id DESC")


@router.post("/api/devices")
async def create_device(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO device (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/devices/{item_id}")
async def get_device(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM device WHERE id = $1", item_id)
