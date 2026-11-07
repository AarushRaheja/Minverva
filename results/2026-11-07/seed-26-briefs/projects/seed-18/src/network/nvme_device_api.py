# src/network/nvme_device_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["nvme_device"])


@router.get("/api/nvme_devices")
async def list_nvme_devices(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM nvme_device ORDER BY id DESC")


@router.post("/api/nvme_devices")
async def create_nvme_device(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO nvme_device (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/nvme_devices/{item_id}")
async def get_nvme_device(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM nvme_device WHERE id = $1", item_id)
