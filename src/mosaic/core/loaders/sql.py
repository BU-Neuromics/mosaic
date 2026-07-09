"""SQLLoader: load records from a SQL query into Mosaic (read-only, safe queries only)."""

import re
from datetime import datetime
from typing import Any, Iterator

from mosaic.core.loaders.base import ConfigurableLoader, RawRecord

# SQL keywords that indicate write operations — these are forbidden.
_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
)

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def validate_read_only_query(query: str) -> None:
    """Raise ValueError if the query contains write/DDL keywords.

    Args:
        query: SQL query string to validate.

    Raises:
        ValueError: If the query contains any of the 7 forbidden keywords.
    """
    match = _FORBIDDEN_PATTERN.search(query)
    if match:
        raise ValueError(
            f"SQLLoader: query contains forbidden keyword '{match.group()}'. "
            "Only read-only SELECT queries are allowed."
        )


class SQLLoader(ConfigurableLoader):
    """Load records from a SQL database into Mosaic.

    Requires ``datahelix-mosaic[loaders-sql]`` (SQLAlchemy>=2.0).

    Only read-only SELECT queries are accepted. Any query containing the
    keywords INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or TRUNCATE
    is rejected before execution.

    Config keys (in addition to ConfigurableLoader keys):
        connection_url (str): SQLAlchemy connection URL.
        query (str): SQL SELECT query to execute.
        params (dict): Optional query parameters.
    """

    name: str = "sql"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._connection_url: str = config.get("connection_url", "")
        self._query: str = config.get("query", "")
        self._params: dict[str, Any] = config.get("params", {})

        if self._query:
            validate_read_only_query(self._query)

    def fetch(
        self,
        since: datetime | None = None,
        **kwargs: Any,
    ) -> Iterator[RawRecord]:
        """Execute the configured query and yield one RawRecord per row.

        Args:
            since: Ignored unless the query uses a :since parameter.
        """
        try:
            import sqlalchemy as sa
        except ImportError as exc:
            raise ImportError(
                "SQLLoader requires sqlalchemy. Install with: pip install 'datahelix-mosaic[loaders-sql]'"
            ) from exc

        validate_read_only_query(self._query)

        engine = sa.create_engine(self._connection_url)
        params = dict(self._params)
        if since is not None:
            params.setdefault("since", since)

        with engine.connect() as conn:
            result = conn.execute(sa.text(self._query), params)
            keys = list(result.keys())
            for row in result:
                yield dict(zip(keys, row))
