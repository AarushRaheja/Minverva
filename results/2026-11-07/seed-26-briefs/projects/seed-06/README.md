# real-time stream processing engine

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `cep_task` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `partition_definition` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [auth/oauth] OAuth start/callback flow that mints the session after the provider returns.
- `t6` [network/rest] REST endpoints for `cep_task`: GET and POST /api/cep_tasks, GET /api/cep_tasks/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `partition_definition`: GET and POST /api/partition_definitions, GET /api/partition_definitions/{item_id}; every handler requires a session.
- `t8` [network/client] Typed TypeScript client for `cep_task` with list/create functions over /api/cep_tasks.
- `t9` [frontend/page] React page at /cep_tasks that fetches /api/cep_tasks and renders rows.
- `t10` [frontend/page] React page at /partition_definitions that fetches /api/partition_definitions and renders rows.
- `t11` [frontend/form] React form component that creates a `cep_task` through the typed client.
- `t12` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t13` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t5, t12
- network: t6, t7, t8
- frontend: t9, t10, t11, t13
