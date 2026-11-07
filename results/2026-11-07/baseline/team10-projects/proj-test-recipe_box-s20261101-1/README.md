# recipe box

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `recipe` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `pantry_item` with an id, owner, timestamps and the columns the API needs.
- `t4` [database/schema] Postgres table `cook` with an id, owner, timestamps and the columns the API needs.
- `t5` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t6` [network/rest] REST endpoints for `recipe`: GET and POST /api/recipes, GET /api/recipes/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `pantry_item`: GET and POST /api/pantry_items, GET /api/pantry_items/{item_id}; every handler requires a session.
- `t8` [network/rest] REST endpoints for `cook`: GET and POST /api/cooks, GET /api/cooks/{item_id}; every handler requires a session.
- `t9` [network/client] Typed TypeScript client for `recipe` with list/create functions over /api/recipes.
- `t10` [frontend/page] React page at /recipes that fetches /api/recipes and renders rows.
- `t11` [frontend/page] React page at /pantry_items that fetches /api/pantry_items and renders rows.
- `t12` [frontend/page] React page at /cooks that fetches /api/cooks and renders rows.
- `t13` [frontend/form] React form component that creates a `recipe` through the typed client.
- `t14` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t15` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3, t4
- auth: t5, t14
- network: t6, t7, t8, t9
- frontend: t10, t11, t12, t13, t15
