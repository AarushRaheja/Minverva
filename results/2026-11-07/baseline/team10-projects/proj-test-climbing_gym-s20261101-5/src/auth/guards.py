# src/auth/guards.py
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from src.auth.session import require_session

PROTECTED_ROUTES = ["/walls", "/belay_checks"]


async def require_route_guard(request, call_next):
    if request.url.path in PROTECTED_ROUTES:
        try:
            await require_session(request)
        except HTTPException as exc:  # an exception raised in middleware would surface as a 500
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)
