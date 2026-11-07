# src/network/video_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["video"])


@router.get("/api/videos")
async def list_videos(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM video ORDER BY id DESC")


@router.post("/api/videos")
async def create_video(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO video (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/videos/{item_id}")
async def get_video(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM video WHERE id = $1", item_id)
