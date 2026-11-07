# src/network/account_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["account"])


@router.get("/api/accounts")
async def list_accounts(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM account ORDER BY id DESC")


@router.post("/api/accounts")
async def create_account(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO account (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/accounts/{item_id}")
async def get_account(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM account WHERE id = $1", item_id)
