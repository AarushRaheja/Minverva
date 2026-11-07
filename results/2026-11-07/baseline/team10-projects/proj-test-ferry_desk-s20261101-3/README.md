# ferry booking desk

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `harbor` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `sailing` with an id, owner, timestamps and the columns the API needs.
- `t4` [database/schema] Postgres table `vessel` with an id, owner, timestamps and the columns the API needs.
- `t5` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t6` [network/rest] REST endpoints for `harbor`: GET and POST /api/harbors, GET /api/harbors/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `sailing`: GET and POST /api/sailings, GET /api/sailings/{item_id}; every handler requires a session.
- `t8` [network/rest] REST endpoints for `vessel`: GET and POST /api/vessels, GET /api/vessels/{item_id}; every handler requires a session.
- `t9` [network/client] Typed TypeScript client for `vessel` with list/create functions over /api/vessels.
- `t10` [frontend/page] React page at /harbors that fetches /api/harbors and renders rows.
- `t11` [frontend/page] React page at /sailings that fetches /api/sailings and renders rows.
- `t12` [frontend/page] React page at /vessels that fetches /api/vessels and renders rows.
- `t13` [frontend/form] React form component that creates a `vessel` through the typed client.
- `t14` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t15` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3, t4
- auth: t5, t14
- network: t6, t7, t8, t9
- frontend: t10, t11, t12, t13, t15
