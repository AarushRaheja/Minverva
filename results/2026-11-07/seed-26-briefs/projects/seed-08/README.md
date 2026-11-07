# high-throughput vector database

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `vector_index` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `metadata_filter` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `vector_index`: GET and POST /api/vector_indices, GET /api/vector_indices/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `metadata_filter`: GET and POST /api/metadata_filters, GET /api/metadata_filters/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `metadata_filter` with list/create functions over /api/metadata_filters.
- `t8` [frontend/page] React page at /vector_indices that fetches /api/vector_indices and renders rows.
- `t9` [frontend/page] React page at /metadata_filters that fetches /api/metadata_filters and renders rows.
- `t10` [frontend/form] React form component that creates a `metadata_filter` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
