# src/network/policy_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["policy"])


@router.get("/api/policys")
async def list_policies(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM policy ORDER BY id DESC")


@router.post("/api/policys")
async def create_policy(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO policy (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/policys/{item_id}")
async def get_policy(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM policy WHERE id = $1", item_id)
