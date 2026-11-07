# src/network/node_repair_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["node_repair"])


@router.get("/api/node_repairs")
async def list_node_repairs(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM node_repair ORDER BY id DESC")


@router.post("/api/node_repairs")
async def create_node_repair(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO node_repair (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/node_repairs/{item_id}")
async def get_node_repair(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM node_repair WHERE id = $1", item_id)
