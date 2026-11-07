# src/network/sensor_fusion_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["sensor_fusion"])


@router.get("/api/sensor_fusions")
async def list_sensor_fusions(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM sensor_fusion ORDER BY id DESC")


@router.post("/api/sensor_fusions")
async def create_sensor_fusion(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO sensor_fusion (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/sensor_fusions/{item_id}")
async def get_sensor_fusion(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM sensor_fusion WHERE id = $1", item_id)
