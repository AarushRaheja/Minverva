# cloud gaming frame-streaming server

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `video` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `input_prediction` with an id, owner, timestamps and the columns the API needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [network/rest] REST endpoints for `video`: GET and POST /api/videos, GET /api/videos/{item_id}; every handler requires a session.
- `t6` [network/rest] REST endpoints for `input_prediction`: GET and POST /api/input_predictions, GET /api/input_predictions/{item_id}; every handler requires a session.
- `t7` [network/client] Typed TypeScript client for `video` with list/create functions over /api/videos.
- `t8` [frontend/page] React page at /videos that fetches /api/videos and renders rows.
- `t9` [frontend/page] React page at /input_predictions that fetches /api/input_predictions and renders rows.
- `t10` [frontend/form] React form component that creates a `video` through the typed client.
- `t11` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t12` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t11
- network: t5, t6, t7
- frontend: t8, t9, t10, t12
