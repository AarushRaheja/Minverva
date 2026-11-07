# src/network/cep_task_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["cep_task"])


@router.get("/api/cep_tasks")
async def list_cep_tasks(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM cep_task ORDER BY id DESC")


@router.post("/api/cep_tasks")
async def create_cep_task(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO cep_task (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/cep_tasks/{item_id}")
async def get_cep_task(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM cep_task WHERE id = $1", item_id)
