# src/network/domain_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["domain"])


@router.get("/api/domains")
async def list_domains(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM domain ORDER BY id DESC")


@router.post("/api/domains")
async def create_domain(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO domain (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/domains/{item_id}")
async def get_domain(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM domain WHERE id = $1", item_id)
