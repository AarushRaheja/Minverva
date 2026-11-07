# src/network/vst3_plugin_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["vst3_plugin"])


@router.get("/api/vst3_plugins")
async def list_vst3_plugins(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM vst3_plugin ORDER BY id DESC")


@router.post("/api/vst3_plugins")
async def create_vst3_plugin(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO vst3_plugin (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/vst3_plugins/{item_id}")
async def get_vst3_plugin(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM vst3_plugin WHERE id = $1", item_id)
