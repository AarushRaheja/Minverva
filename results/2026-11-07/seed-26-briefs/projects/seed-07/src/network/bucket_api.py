# src/network/bucket_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["bucket"])


@router.get("/api/buckets")
async def list_buckets(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM bucket ORDER BY id DESC")


@router.post("/api/buckets")
async def create_bucket(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO bucket (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/buckets/{item_id}")
async def get_bucket(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM bucket WHERE id = $1", item_id)
