# src/network/raft_log_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["raft_log"])


@router.get("/api/raft_logs")
async def list_raft_logs(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM raft_log ORDER BY id DESC")


@router.post("/api/raft_logs")
async def create_raft_log(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO raft_log (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/raft_logs/{item_id}")
async def get_raft_log(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM raft_log WHERE id = $1", item_id)
