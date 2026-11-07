# src/network/observation_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["observation"])


@router.get("/api/observations")
async def list_observations(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM observation ORDER BY id DESC")


@router.post("/api/observations")
async def create_observation(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO observation (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/observations/{item_id}")
async def get_observation(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM observation WHERE id = $1", item_id)
