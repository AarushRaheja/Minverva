# distributed transactional key-value store

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `bucket` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `raft_log` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `bucket`: GET and POST /api/buckets, GET /api/buckets/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `raft_log`: GET and POST /api/raft_logs, GET /api/raft_logs/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `bucket` with list/create functions over /api/buckets.
- `t8` [frontend/page] React page at /buckets that fetches /api/buckets and renders rows.
- `t9` [frontend/page] React page at /raft_logs that fetches /api/raft_logs and renders rows.
- `t10` [frontend/form] React form component that creates a `bucket` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
