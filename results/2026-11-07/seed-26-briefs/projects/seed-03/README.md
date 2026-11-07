# event-driven usage-based billing platform with sliding-window metering and dynamic invoice generation

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the app needs.
- `t2` [database/schema] Postgres table `event_invoice` with an id, owner, timestamps and the columns the app needs.
- `t3` [database/schema] Postgres table `transaction` with an id, owner, timestamps and the columns the app needs.
- `t4` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t5` [auth/oauth] OAuth hand-off: a `start_oauth` function that mints the session after the provider returns.
- `t6` [network/rest] REST endpoints for `event_invoice`: GET and POST /api/event_invoices, GET /api/event_invoices/{item_id}; every handler requires a session.
- `t7` [network/rest] REST endpoints for `transaction`: GET and POST /api/transactions, GET /api/transactions/{item_id}; every handler requires a session.
- `t8` [network/client] Typed TypeScript client for `event_invoice` with list/create functions over /api/event_invoices.
- `t9` [frontend/page] React page at /accounts that requires a session and provides the route handler.
- `t10` [frontend/page] React page at /transactions that requires a session and provides the route handler.
- `t11` [frontend/form] React form component that creates a `event_invoice` through the typed client.
- `t12` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t13` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2, t3
- auth: t4, t5, t12
- network: t6, t7, t8
- frontend: t9, t10, t11, t13
