# high-performance asynchronous IO event loop framework for Linux utilizing zero-copy io_uring ring buffers

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `session` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] OAuth start/callback table with the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `session` table with an id, owner, timestamps and the columns the API needs.
- `t5` [auth/oauth] OAuth start/callback table with the columns the API needs.
- `t6` [network/rest] REST endpoints for `event`: GET and POST /api/events, GET /api/events/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `ring_buffer`: GET and POST /api/ring_buffers, GET /api/ring_buffers/{item_id}; every handler requires a session.
- `t8` [network/client] Typed TypeScript client for `event` with list/create functions over /api/events.
- `t9` [frontend/page] React page at /events that fetches /api/events and renders rows.
- `t10` [frontend/page] React page at /ring_buffers that fetches /api/ring_buffers and renders rows.
- `t11` [frontend/form] React form component that creates a `event` through the typed client.
- `t12` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t13` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t5, t12
- network: t6, t7, t8
- frontend: t9, t10, t11, t13
