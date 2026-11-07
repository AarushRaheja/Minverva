# src/network/model_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["model"])


@router.get("/api/models")
async def list_models(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM model ORDER BY id DESC")


@router.post("/api/models")
async def create_model(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO model (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/models/{item_id}")
async def get_model(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM model WHERE id = $1", item_id)
