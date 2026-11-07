# bake

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `dough_mix` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `baker` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `dough_mix`: GET and POST /api/dough_mixes, GET /api/dough_mixes/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `baker`: GET and POST /api/bakers, GET /api/bakers/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `dough_mix` with list/create functions over /api/dough_mixes.
- `t8` [frontend/page] React page at /dough_mixes that fetches /api/dough_mixes and renders rows.
- `t9` [frontend/page] React page at /bakers that fetches /api/bakers and renders rows.
- `t10` [frontend/form] React form component that creates a `dough_mix` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
