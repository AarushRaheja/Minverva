# src/network/order_book_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["order_book"])


@router.get("/api/order_books")
async def list_order_books(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM order_book ORDER BY id DESC")


@router.post("/api/order_books")
async def create_order_book(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO order_book (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/order_books/{item_id}")
async def get_order_book(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM order_book WHERE id = $1", item_id)
