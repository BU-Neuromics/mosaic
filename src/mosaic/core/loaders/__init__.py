"""Unified ingestion loader framework for Mosaic.

All data loading into Mosaic — reference loaders, Cappella adapters, CLI ingest —
subclasses EntityLoader from this package.
"""

from mosaic.core.loaders.base import (
    ConfigurableLoader,
    EntityLoader,
    IngestResult,
    RawRecord,
    TransformedRecord,
)
from mosaic.core.loaders.csv import CSVLoader
from mosaic.core.loaders.json import JSONLoader
from mosaic.core.loaders.pipeline import IngestPipeline

__all__ = [
    "EntityLoader",
    "ConfigurableLoader",
    "RawRecord",
    "TransformedRecord",
    "IngestResult",
    "IngestPipeline",
    "CSVLoader",
    "JSONLoader",
]
