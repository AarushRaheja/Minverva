# ski patrol log

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `patroller` with an id, owner, timestamps and the columns the API needs.
- `t3` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t4` [network/rest] REST endpoints for `patroller`: GET and POST /api/patrollers, GET /api/patrollers/{item_id}; every handler requires a session.
- `t5` [network/client] Typed TypeScript client for `patroller` with list/create functions over /api/patrollers.
- `t6` [frontend/page] React page at /patrollers that fetches /api/patrollers and renders rows.
- `t7` [frontend/form] React form component that creates a `patroller` through the typed client.
- `t8` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t9` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2
- auth: t3, t8
- network: t4, t5
- frontend: t6, t7, t9
