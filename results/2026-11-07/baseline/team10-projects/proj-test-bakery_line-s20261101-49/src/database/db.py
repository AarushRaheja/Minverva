import asyncio
import os

import asyncpg

DSN = os.environ.get("DATABASE_URL", "postgresql://localhost/app")


class Database:
    """Connects on first use, because a pool has to be created inside a running event loop."""

    def __init__(self):
        self._pool = None
        self._lock = asyncio.Lock()

    async def _connected(self):
        async with self._lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(DSN)
        return self._pool

    async def fetch(self, sql: str, *args) -> list[dict]:
        pool = await self._connected()
        return [dict(row) for row in await pool.fetch(sql, *args)]

    async def fetchrow(self, sql: str, *args) -> dict | None:
        pool = await self._connected()
        row = await pool.fetchrow(sql, *args)
        return dict(row) if row else None


db = Database()
