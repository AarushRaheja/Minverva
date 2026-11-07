# src/network/input_prediction_api.py
from fastapi import APIRouter, Depends

from src.auth.session import require_session
from src.database.db import db

router = APIRouter(tags=["input_prediction"])


@router.get("/api/input_predictions")
async def list_input_predictions(user: dict = Depends(require_session)):
    return await db.fetch("SELECT * FROM input_prediction ORDER BY id DESC")


@router.post("/api/input_predictions")
async def create_input_prediction(payload: dict, user: dict = Depends(require_session)):
    return await db.fetchrow(
        "INSERT INTO input_prediction (owner_id, title) VALUES ($1, $2) RETURNING *",
        user["id"], payload.get("title"),
    )


@router.get("/api/input_predictions/{item_id}")
async def get_input_prediction(item_id: int, user: dict = Depends(require_session)):
    return await db.fetchrow("SELECT * FROM input_prediction WHERE id = $1", item_id)
