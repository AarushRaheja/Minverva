# src/network/transaction_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["transaction"])


@router.get("/api/transactions")
async def list_transactions(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM transaction ORDER BY id DESC")


@router.post("/api/transactions")
async def create_transaction(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO transaction (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/transactions/{item_id}")
async def get_transaction(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM transaction WHERE id = $1", item_id)
