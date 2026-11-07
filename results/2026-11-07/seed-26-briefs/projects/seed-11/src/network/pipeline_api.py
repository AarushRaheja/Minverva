# src/network/pipeline_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["pipeline"])


@router.get("/api/pipelines")
async def list_pipelines(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM pipeline ORDER BY id DESC")


@router.post("/api/pipelines")
async def create_pipeline(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO pipeline (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/pipelines/{item_id}")
async def get_pipeline(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM pipeline WHERE id = $1", item_id)
