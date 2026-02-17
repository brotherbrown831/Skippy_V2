"""Database utilities for connection pool management."""
from contextlib import asynccontextmanager
from typing import Optional

# Global connection pool reference (set by main.py at startup)
_db_pool: Optional[object] = None


def set_db_pool(pool):
    """Set the global database connection pool (called by main.py at startup)."""
    global _db_pool
    _db_pool = pool


def get_db_pool():
    """Get the global database connection pool."""
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized. Call set_db_pool() at startup.")
    return _db_pool


@asynccontextmanager
async def get_db_connection():
    """Get a database connection from the global pool (works anywhere).

    Usage:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM table")
    """
    pool = get_db_pool()
    async with pool.connection() as conn:
        yield conn
