# custom PCIe NVMe controller driver

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `nvme_device` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `thermal_profile` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `nvme_device`: GET and POST /api/nvme_devices, GET /api/nvme_devices/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `thermal_profile`: GET and POST /api/thermal_profiles, GET /api/thermal_profiles/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `nvme_device` with list/create functions over /api/nvme_devices.
- `t8` [frontend/page] React page at /nvme_devices that fetches /api/nvme_devices and renders rows.
- `t9` [frontend/page] React page at /thermal_profiles that fetches /api/thermal_profiles and renders rows.
- `t10` [frontend/form] React form component that creates a `nvme_device` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
