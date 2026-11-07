# Create a distributed SQL query coordinator featuring vectorized SIMD execution over partitioned Parquet datasets.

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `table_town` with an id, owner, timestamps and the columns the API needs.
- `t3` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t4` [auth/oauth] OAuth hand-off: a `start_oauth` function that mints the session after the provider returns.
- `t5` [network/rest] REST endpoints for `table_town`: GET and POST /api/tables, GET /api/tables/{item_id}; every handler requires a session.
- `t6` [network/client] Typed TypeScript client for `table_town` with list/create functions over /api/tables.
- `t7` [frontend/page] React page at /tables that fetches /api/tables and renders rows.
- `t8` [frontend/form] React form component that creates a `table_town` through the typed client.
- `t9` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t10` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2
- auth: t3, t4, t9
- network: t5, t6
- frontend: t7, t8, t10
