# src/network/tool_sandbox_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["tool_sandbox"])


@router.get("/api/tool_sandboxes")
async def list_tool_sandboxes(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM tool_sandbox ORDER BY id DESC")


@router.post("/api/tool_sandboxes")
async def create_tool_sandbox(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO tool_sandbox (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/tool_sandboxes/{item_id}")
async def get_tool_sandbox(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM tool_sandbox WHERE id = $1", item_id)
