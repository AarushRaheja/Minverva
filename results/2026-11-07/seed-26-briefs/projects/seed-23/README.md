# construct a ultra-low-latency financial matching engine handling FIX protocol order books with sub-microsecond execution

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `order_book` with an id, owner, timestamps and the columns the API needs.
- `t3` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t4` [network/rest] REST endpoints for `order_book`: GET and POST /api/order_books, GET /api/order_books/{item_id}; every handler requires a session.
- `t5` [network/client] Typed TypeScript client for `order_book` with list/create functions over /api/order_books.
- `t6` [frontend/page] React page at /order_books that fetches /api/order_books and renders rows.
- `t7` [frontend/form] React form component that creates a `order_book` through the typed client.
- `t8` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t9` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2
- auth: t3, t8
- network: t4, t5
- frontend: t6, t7, t9
