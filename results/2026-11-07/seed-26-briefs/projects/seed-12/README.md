# autonomous AI agent sandbox environment

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `state_checkpoint` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `tool_sandbox` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [auth/oauth] OAuth start/callback flow that mints the session after the provider returns.
- `t6` [network/rest] REST endpoints for `state_checkpoint`: GET and POST /api/state_checkcases, GET /api/state_checkcases/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `tool_sandbox`: GET and POST /api/tool_sandboxes, GET /api/tool_sandboxes/{item_id}; every handler requires a session.
- `t8` [network/client] Typed TypeScript client for `state_checkpoint` with list/create functions over /api/state_checkcases.
- `t9` [frontend/page] React page at /state_checkcases that fetches /api/state_checkcases and renders rows.
- `t10` [frontend/page] React page at /tool_sandboxes that fetches /api/tool_sandboxes and renders rows.
- `t11` [frontend/form] React form component that creates a `state_checkpoint` through the typed client.
- `t12` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t13` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t5, t12
- network: t6, t7, t8
- frontend: t9, t10, t11, t13
