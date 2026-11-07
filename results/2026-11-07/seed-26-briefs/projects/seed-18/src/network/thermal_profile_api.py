# src/network/thermal_profile_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["thermal_profile"])


@router.get("/api/thermal_profiles")
async def list_thermal_profiles(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM thermal_profile ORDER BY id DESC")


@router.post("/api/thermal_profiles")
async def create_thermal_profile(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO thermal_profile (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/thermal_profiles/{item_id}")
async def get_thermal_profile(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM thermal_profile WHERE id = $1", item_id)
