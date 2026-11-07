from fastapi import FastAPI
from src.auth.session import require_session
from src.auth.guards import require_route_guard
from src.database.db import db
from src.network.account_api import router as account_router

app = FastAPI(title="Construct an Identity Provider (IdP) supporting SAML 2.0/OIDC federation, FIDO2 WebAuthn, and token revocation.")
app.middleware("http")(require_route_guard)
app.include_router(account_router)

# Frontend pages are built from src/frontend/ and served as static assets.
