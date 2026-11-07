# src/network/metadata_filter_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["metadata_filter"])


@router.get("/api/metadata_filters")
async def list_metadata_filters(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM metadata_filter ORDER BY id DESC")


@router.post("/api/metadata_filters")
async def create_metadata_filter(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO metadata_filter (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/metadata_filters/{item_id}")
async def get_metadata_filter(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM metadata_filter WHERE id = $1", item_id)
