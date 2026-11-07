# vineyard ledger

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `barrel` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `vine` with an id, owner, timestamps and the columns the API needs.
- `t4` [database/schema] Postgres table `cellar` with an id, owner, timestamps and the columns the API needs.
- `t5` [database/schema] Postgres table `vintage` with an id, owner, timestamps and the columns the API needs.
- `t6` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t7` [network/rest] REST endpoints for `barrel`: GET and POST /api/barrels, GET /api/barrels/{item_id}; every handler requires a session.
- `t8` [network/rest] REST endpoints for `vine`: GET and POST /api/vines, GET /api/vines/{item_id}; every handler requires a session.
- `t9` [network/rest] REST endpoints for `cellar`: GET and POST /api/cellars, GET /api/cellars/{item_id}; every handler requires a session.
- `t10` [network/rest] REST endpoints for `vintage`: GET and POST /api/vintages, GET /api/vintages/{item_id}; every handler requires a session.
- `t11` [network/client] Typed TypeScript client for `vintage` with list/create functions over /api/vintages.
- `t12` [frontend/page] React page at /barrels that fetches /api/barrels and renders rows.
- `t13` [frontend/page] React page at /vines that fetches /api/vines and renders rows.
- `t14` [frontend/page] React page at /cellars that fetches /api/cellars and renders rows.
- `t15` [frontend/page] React page at /vintages that fetches /api/vintages and renders rows.
- `t16` [frontend/form] React form component that creates a `vintage` through the typed client.
- `t17` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t18` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3, t4, t5
- auth: t6, t17
- network: t7, t8, t9, t10, t11
- frontend: t12, t13, t14, t15, t16, t18
