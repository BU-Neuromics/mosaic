"""CSVLoader: load tabular data from a file path, HTTP URL, or raw bytes."""

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from mosaic.core.loaders.base import ConfigurableLoader, RawRecord


class CSVLoader(ConfigurableLoader):
    """Load CSV records into Mosaic.

    Supports three source modes set via config:
    - ``file``: path to a local CSV file (config key ``source_file``)
    - ``http``: HTTP/HTTPS URL (config key ``source_url``, requires ``requests``)
    - ``bytes``: raw bytes passed in at fetch() time via ``data`` kwarg

    Config keys (in addition to ConfigurableLoader keys):
        source_file (str): Path to a CSV file.
        source_url (str): HTTP/HTTPS URL to fetch CSV from.
        encoding (str): Character encoding (default "utf-8").
    """

    name: str = "csv"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._source_file: str | None = config.get("source_file")
        self._source_url: str | None = config.get("source_url")
        self._encoding: str = config.get("encoding", "utf-8")

    def fetch(
        self,
        since: datetime | None = None,
        data: bytes | None = None,
        **kwargs: Any,
    ) -> Iterator[RawRecord]:
        """Yield one RawRecord per CSV data row.

        Args:
            since: Ignored (CSV has no incremental support).
            data: Raw bytes to parse instead of reading from file/URL.
        """
        if data is not None:
            text = data.decode(self._encoding)
            yield from self._parse_text(text)
        elif self._source_url:
            yield from self._fetch_url()
        elif self._source_file:
            yield from self._fetch_file(Path(self._source_file))
        else:
            raise ValueError("CSVLoader: no source configured (source_file, source_url, or data)")

    def _fetch_file(self, path: Path) -> Iterator[RawRecord]:
        with open(path, newline="", encoding=self._encoding) as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield dict(row)

    def _fetch_url(self) -> Iterator[RawRecord]:
        try:
            import requests
        except ImportError as exc:
            raise ImportError(
                "CSVLoader HTTP source requires 'requests'. Install it with: pip install requests"
            ) from exc
        resp = requests.get(self._source_url, timeout=30)
        resp.raise_for_status()
        yield from self._parse_text(resp.text)

    def _parse_text(self, text: str) -> Iterator[RawRecord]:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            yield dict(row)
