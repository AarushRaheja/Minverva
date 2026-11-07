# spatial 3D audio rendering pipeline streaming low-latency multi-user audio over WebSockets and WebRTC

Stack: fastapi+react+postgres

## Tasks
- `t1` [database/schema] Postgres table `users` with an id, owner, timestamps and the columns the API needs.
- `t2` [database/schema] Postgres table `audio_track` with an id, owner, timestamps and the columns the API needs.
- `t3` [auth/session] Session cookie auth: a `require_session` dependency that loads the user row.
- `t4` [auth/oauth] OAuth start/callback flow that mints the session after the provider returns.
- `t5` [network/rest] REST endpoints for `audio_track`: GET and POST /api/audio_tracks, GET /api/audio_tracks/{item_id}; every handler requires a session.
- `t6` [network/client] Typed TypeScript client for `audio_track` with list/create functions over /api/audio_tracks.
- `t7` [frontend/page] React page at /audio_tracks that fetches /api/audio_tracks and renders rows.
- `t8` [frontend/form] React form component that creates a `audio_track` through the typed client.
- `t9` [auth/guards] Route guard that rejects signed-out users for every protected frontend route.
- `t10` [frontend/layout] App shell: navigation to every page and the page components rendered inside it.

## Domains
- database: t1, t2
- auth: t3, t4, t9
- network: t5, t6
- frontend: t7, t8, t10
