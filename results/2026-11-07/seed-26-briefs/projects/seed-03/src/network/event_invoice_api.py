# src/network/event_invoice_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["event_invoice"])


@router.get("/api/event_invoices")
async def list_event_invoices(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM event_invoice ORDER BY id DESC")


@router.post("/api/event_invoices")
async def create_event_invoice(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO event_invoice (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/event_invoices/{item_id}")
async def get_event_invoice(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM event_invoice WHERE id = $1", item_id)
