# src/network/audio_track_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["audio_track"])


@router.get("/api/audio_tracks")
async def list_audio_tracks(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM audio_track ORDER BY id DESC")


@router.post("/api/audio_tracks")
async def create_audio_track(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO audio_track (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/audio_tracks/{item_id}")
async def get_audio_track(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM audio_track WHERE id = $1", item_id)
