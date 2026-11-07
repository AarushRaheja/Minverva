# src/network/account_request_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["account_request"])


@router.get("/api/account_requests")
async def list_account_requests(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM account_request ORDER BY id DESC")


@router.post("/api/account_requests")
async def create_account_request(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO account_request (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/account_requests/{item_id}")
async def get_account_request(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM account_request WHERE id = $1", item_id)
