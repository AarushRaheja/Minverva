# src/auth/session.py
from fastapi import HTTPException, Request

from src.database.db import db

SESSION_COOKIE = "app_session"


async def require_session(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="signed out")
    user = await db.fetchrow("SELECT * FROM users WHERE session_token = $1", token)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown session")
    return dict(user)
