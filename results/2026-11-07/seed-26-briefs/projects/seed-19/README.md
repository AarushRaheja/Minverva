# peer-to-peer overlay network

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `account_provider` with an id, owner, timestamps and the columns the API needs.
- `t3` [database/schema] Postgres table `account_request` with an id, owner, timestamps and the columns the API needs.
- `t4` [database/schema] Postgres table `session_token` with an id, owner, timestamps and the columns the API needs.
- `t5` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t6` [network/rest] REST endpoints for `account_provider`: GET and POST /api/account_providers, GET /api/account_providers/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `account_request`: GET and POST /api/account_requests, GET /api/account_requests/{item_id}; every handler requires a session.
- `t8` [network/client] Typed TypeScript client for `user` with list/create functions over /api/users.
- `t9` [frontend/page] React page at /accounts that fetches /api/account_providers and renders rows.
- `t10` [frontend/page] React page at /users that fetches /api/account_requests and renders rows.
- `t11` [frontend/form] React form component that creates a `user` through the typed client.
- `t12` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t13` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3, t4
- auth: t5, t12
- network: t6, t7, t8
- frontend: t9, t10, t11, t13
