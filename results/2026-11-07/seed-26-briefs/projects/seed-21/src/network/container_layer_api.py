# src/network/container_layer_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["container_layer"])


@router.get("/api/container_layers")
async def list_container_layers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM container_layer ORDER BY id DESC")


@router.post("/api/container_layers")
async def create_container_layer(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO container_layer (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/container_layers/{item_id}")
async def get_container_layer(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM container_layer WHERE id = $1", item_id)
