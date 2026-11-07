"""The harness's database layer for run checks: the asyncpg-style pool every project is told to import."""
import os

import asyncpg


class _Acquire:
    """`async with db.acquire() as conn`, or `conn = await db.acquire()` then `await db.release(conn)`, as in asyncpg."""

    def __init__(self, owner):
        self._owner = owner
        self._conn = None

    async def _take(self):
        self._conn = await (await self._owner._get()).acquire()
        return self._conn

    def __await__(self):
        return self._take().__await__()

    async def __aenter__(self):
        return await self._take()

    async def __aexit__(self, *exc):
        await self._owner.release(self._conn)


class _Pool:
    def __init__(self):
        self._pool = None
        self._loop = None

    async def _get(self):
        import asyncio
        loop = asyncio.get_running_loop()
        if self._pool is None or self._loop is not loop:
            self._pool = await asyncpg.create_pool(os.environ["SLM_PG_DSN"], min_size=1, max_size=4)
            self._loop = loop
        return self._pool

    def acquire(self):
        return _Acquire(self)

    async def release(self, conn):
        await (await self._get()).release(conn)

    async def executemany(self, sql, args):
        return await (await self._get()).executemany(sql, args)

    async def fetch(self, sql, *args):
        return [dict(r) for r in await (await self._get()).fetch(sql, *args)]

    async def fetchrow(self, sql, *args):
        row = await (await self._get()).fetchrow(sql, *args)
        return dict(row) if row is not None else None

    async def fetchval(self, sql, *args):
        return await (await self._get()).fetchval(sql, *args)

    async def execute(self, sql, *args):
        return await (await self._get()).execute(sql, *args)


db = _Pool()


async def fetch(sql, *args):
    return await db.fetch(sql, *args)


async def fetchrow(sql, *args):
    return await db.fetchrow(sql, *args)


async def execute(sql, *args):
    return await db.execute(sql, *args)
