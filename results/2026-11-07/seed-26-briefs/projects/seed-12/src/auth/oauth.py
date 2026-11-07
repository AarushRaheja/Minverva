# src/auth/oauth.py
from src.auth.session import require_session

AUTHORIZE_URL = "https://accounts.example.com/authorize"
TOKEN_URL = "https://accounts.example.com/token"


async def oauth_start(request):
    """Begin the provider hand-off; the callback below mints the session."""
    return {"redirect": AUTHORIZE_URL, "state": request.headers.get("x-request-id")}


async def oauth_callback(request):
    user = await require_session(request)
    return {"signed_in": user["email"]}
