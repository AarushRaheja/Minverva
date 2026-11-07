# object storage engine

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `chunk` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `node_repair` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `chunk`: GET and POST /api/chunks, GET /api/chunks/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `node_repair`: GET and POST /api/node_repair, GET /api/node_repair/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `chunk` with list/create functions over /api/chunks.
- `t8` [frontend/page] React page at /chunks that fetches /api/chunks and renders rows.
- `t9` [frontend/page] React page at /node_repair that fetches /api/node_repair and renders rows.
- `t10` [frontend/form] React form component that creates a `chunk` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
