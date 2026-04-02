"""Storage adapters for Hippo.

SQLite adapter is always available.
PostgreSQL adapter requires psycopg[pool] — install with: pip install hippo[postgres]
"""

from .sqlite_adapter import SQLiteAdapter

__all__ = ["SQLiteAdapter"]

try:
    from .postgres_adapter import PostgresAdapter

    __all__.append("PostgresAdapter")
except ImportError:
    pass
