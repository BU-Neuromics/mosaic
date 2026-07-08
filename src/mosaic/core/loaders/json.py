"""JSONLoader: load JSON array files into Mosaic, with optional JSONPath support."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from mosaic.core.loaders.base import ConfigurableLoader, RawRecord


class JSONLoader(ConfigurableLoader):
    """Load JSON array records into Mosaic.

    By default, the source file must contain a JSON array at the top level.
    Optional JSONPath support (requires ``datahelix-mosaic[loaders-json]``) allows
    extracting records from nested JSON structures.

    Config keys (in addition to ConfigurableLoader keys):
        source_file (str): Path to a JSON file.
        jsonpath (str): JSONPath expression to extract records from nested JSON.
                        Requires ``jsonpath-ng`` (datahelix-mosaic[loaders-json]).
        encoding (str): Character encoding (default "utf-8").
    """

    name: str = "json"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._source_file: str | None = config.get("source_file")
        self._jsonpath: str | None = config.get("jsonpath")
        self._encoding: str = config.get("encoding", "utf-8")

    def fetch(
        self,
        since: datetime | None = None,
        data: bytes | None = None,
        **kwargs: Any,
    ) -> Iterator[RawRecord]:
        """Yield one RawRecord per JSON object in the array.

        Args:
            since: Ignored (JSON files have no incremental support).
            data: Raw bytes to parse instead of reading from file.
        """
        if data is not None:
            parsed = json.loads(data.decode(self._encoding))
        elif self._source_file:
            path = Path(self._source_file)
            with open(path, encoding=self._encoding) as fh:
                parsed = json.load(fh)
        else:
            raise ValueError("JSONLoader: no source configured (source_file or data)")

        records = self._extract_records(parsed)
        for record in records:
            if isinstance(record, dict):
                yield record

    def _extract_records(self, parsed: Any) -> list:
        if self._jsonpath:
            try:
                from jsonpath_ng import parse as jsonpath_parse
            except ImportError as exc:
                raise ImportError(
                    "JSONLoader jsonpath support requires jsonpath-ng. "
                    "Install with: pip install 'datahelix-mosaic[loaders-json]'"
                ) from exc
            expr = jsonpath_parse(self._jsonpath)
            return [match.value for match in expr.find(parsed)]

        if isinstance(parsed, list):
            return parsed
        raise ValueError("JSONLoader: JSON must be an array at the top level (or use jsonpath)")
