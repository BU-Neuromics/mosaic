"""Storage adapters for Mosaic.

SQLite adapter is always available.
PostgreSQL adapter requires psycopg[pool] — install with: pip install datahelix-mosaic[postgres]
"""

from .sqlite_adapter import SQLiteAdapter

__all__ = ["SQLiteAdapter"]

try:
    from .postgres_adapter import PostgresAdapter

    __all__.append("PostgresAdapter")
except ImportError:
    pass
