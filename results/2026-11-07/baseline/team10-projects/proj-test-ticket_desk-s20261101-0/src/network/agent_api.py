# src/network/agent_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["agent"])


@router.get("/api/agents")
async def list_agents(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM agent ORDER BY id DESC")


@router.post("/api/agents")
async def create_agent(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO agent (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/agents/{item_id}")
async def get_agent(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM agent WHERE id = $1", item_id)
