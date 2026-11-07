# Construct an Identity Provider (IdP) supporting SAML 2.0/OIDC federation, FIDO2 WebAuthn, and token revocation.

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `account` with an id, owner, timestamps and the columns the API needs.
- `t3` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t4` [auth/oauth] OAuth start/callback flow that mints the session after the provider returns.
- `t5` [network/rest] REST endpoints for `account`: GET and POST /api/accounts, GET /api/accounts/{item_id}; every handler requires a session.
- `t6` [network/client] Typed TypeScript client for `account` with list/create functions over /api/accounts.
- `t7` [frontend/page] React page at /accounts that fetches /api/accounts and renders rows.
- `t8` [frontend/form] React form component that creates a `account` through the typed client.
- `t9` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t10` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2
- auth: t3, t4, t9
- network: t5, t6
- frontend: t7, t8, t10
