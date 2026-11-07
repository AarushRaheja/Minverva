# autonomous flight controller firmware

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `device` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `sensor_fusion` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `device`: GET and POST /api/devices, GET /api/devices/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `sensor_fusion`: GET and POST /api/sensor_fusions, GET /api/sensor_fusions/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `device` with list/create functions over /api/devices.
- `t8` [frontend/page] React page at /devices that fetches /api/devices and renders rows.
- `t9` [frontend/page] React page at /sensor_fusions that fetches /api/sensor_fusions and renders rows.
- `t10` [frontend/form] React form component that creates a `device` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
