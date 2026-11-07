# real-time audio dsp framework

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `buffer` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `vst3_plugin` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `buffer`: GET and POST /api/buffers, GET /api/buffers/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `vst3_plugin`: GET and POST /api/vst3_plugins, GET /api/vst3_plugins/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `buffer` with list/create functions over /api/buffers.
- `t8` [frontend/page] React page at /buffers that fetches /api/buffers and renders rows.
- `t9` [frontend/page] React page at /vst3_plugins that fetches /api/vst3_plugins and renders rows.
- `t10` [frontend/form] React form component that creates a `buffer` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
