# automated vulnerability scanner

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `vulnerability_report` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `container_layer` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `vulnerability_report`: GET and POST /api/vulnerability_reports, GET /api/vulnerability_reports/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `container_layer`: GET and POST /api/container_layers, GET /api/container_layers/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `vulnerability_report` with list/create functions over /api/vulnerability_reports.
- `t8` [frontend/page] React page at /vulnerability_reports that fetches /api/vulnerability_reports and renders rows.
- `t9` [frontend/page] React page at /container_layers that fetches /api/container_layers and renders rows.
- `t10` [frontend/form] React form component that creates a `vulnerability_report` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
