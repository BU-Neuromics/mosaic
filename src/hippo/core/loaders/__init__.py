"""Unified ingestion loader framework for Hippo.

All data loading into Hippo — reference loaders, Cappella adapters, CLI ingest —
subclasses EntityLoader from this package.
"""

from hippo.core.loaders.base import (
    ConfigurableLoader,
    EntityLoader,
    IngestResult,
    RawRecord,
    TransformedRecord,
)
from hippo.core.loaders.csv import CSVLoader
from hippo.core.loaders.entity_yaml import EntityYAMLLoader
from hippo.core.loaders.json import JSONLoader
from hippo.core.loaders.pipeline import IngestPipeline

__all__ = [
    "EntityLoader",
    "ConfigurableLoader",
    "RawRecord",
    "TransformedRecord",
    "IngestResult",
    "IngestPipeline",
    "CSVLoader",
    "JSONLoader",
    "EntityYAMLLoader",
]
