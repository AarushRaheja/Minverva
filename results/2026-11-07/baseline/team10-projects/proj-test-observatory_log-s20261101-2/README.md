# observatory log

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `comet` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `astronomer` with an id, owner, timestamps and the columns the API needs.
- `t4` [database/schema] Postgres table `observation` with an id, owner, timestamps and the columns the API needs.
- `t5` [database/schema] Postgres table `telescope` with an id, owner, timestamps and the columns the API needs.
- `t6` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t7` [network/rest] REST endpoints for `comet`: GET and POST /api/comets, GET /api/comets/{item_id}; every handler requires a session.
- `t8` [network/rest] REST endpoints for `astronomer`: GET and POST /api/astronomers, GET /api/astronomers/{item_id}; every handler requires a session.
- `t9` [network/rest] REST endpoints for `observation`: GET and POST /api/observations, GET /api/observations/{item_id}; every handler requires a session.
- `t10` [network/rest] REST endpoints for `telescope`: GET and POST /api/telescopes, GET /api/telescopes/{item_id}; every handler requires a session.
- `t11` [network/client] Typed TypeScript client for `telescope` with list/create functions over /api/telescopes.
- `t12` [frontend/page] React page at /comets that fetches /api/comets and renders rows.
- `t13` [frontend/page] React page at /astronomers that fetches /api/astronomers and renders rows.
- `t14` [frontend/page] React page at /observations that fetches /api/observations and renders rows.
- `t15` [frontend/page] React page at /telescopes that fetches /api/telescopes and renders rows.
- `t16` [frontend/form] React form component that creates a `telescope` through the typed client.
- `t17` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t18` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3, t4, t5
- auth: t6, t17
- network: t7, t8, t9, t10, t11
- frontend: t12, t13, t14, t15, t16, t18
