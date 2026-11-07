# src/network/account_provider_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["account_provider"])


@router.get("/api/account_providers")
async def list_account_providers(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM account_provider ORDER BY id DESC")


@router.post("/api/account_providers")
async def create_account_provider(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO account_provider (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/account_providers/{item_id}")
async def get_account_provider(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM account_provider WHERE id = $1", item_id)
