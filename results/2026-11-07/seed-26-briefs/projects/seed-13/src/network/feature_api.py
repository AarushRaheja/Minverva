# src/network/feature_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["feature"])


@router.get("/api/features")
async def list_features(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM feature ORDER BY id DESC")


@router.post("/api/features")
async def create_feature(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO feature (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/features/{item_id}")
async def get_feature(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM feature WHERE id = $1", item_id)
