# distributed LLM training orchestrator

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `pipeline` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `deepspeed_zero_three` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `pipeline`: GET and POST /api/pipelines, GET /api/pipelines/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `deepspeed_zero_three`: GET and POST /api/deepspeed_zero_threes, GET /api/deepspeed_zero_threes/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `pipeline` with list/create functions over /api/pipelines.
- `t8` [frontend/page] React page at /pipelines that fetches /api/pipelines and renders rows.
- `t9` [frontend/page] React page at /deepspeed_zero_threes that fetches /api/deepspeed_zero_threes and renders rows.
- `t10` [frontend/form] React form component that creates a `pipeline` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
