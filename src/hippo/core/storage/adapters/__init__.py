"""SQLite storage adapter with WAL mode support and provenance immutability triggers."""

from .sqlite_adapter import SQLiteAdapter

__all__ = ["SQLiteAdapter"]
