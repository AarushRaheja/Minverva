# src/network/partition_definition_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["partition_definition"])


@router.get("/api/partition_definitions")
async def list_partition_definitions(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM partition_definition ORDER BY id DESC")


@router.post("/api/partition_definitions")
async def create_partition_definition(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO partition_definition (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/partition_definitions/{item_id}")
async def get_partition_definition(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM partition_definition WHERE id = $1", item_id)
