"""ReferenceLoader ABC and LoadResult dataclass.

Surface for reference-data plugins (e.g. ``hippo-reference-fma``,
``hippo-reference-ensembl``). The contract is fixed by Hippo design
spec §2.14 (`hippo/design/sec2_architecture.md`) and decisions D2.14.A–I
in `hippo/design/sec9_decisions.md`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import typer
from pydantic import BaseModel

if TYPE_CHECKING:
    from hippo.core.client import HippoClient
    from hippo.core.validation.validators import ValidationResult


@dataclass
class LoadResult:
    """Outcome of a single :meth:`ReferenceLoader.load` or
    :meth:`ReferenceLoader.upgrade` invocation.

    ``entity_type`` lets multi-class loaders report per-class counts by
    returning one :class:`LoadResult` per entity type (or by aggregating
    if the caller does not need the breakdown).
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    entity_type: str | None = None
    # IDs of entities the loader wrote during this invocation. Populated
    # by loaders that want ``hippo reference upgrade --prune-old`` to be
    # able to remove the prior version's rows after a successful
    # upgrade. Empty when the loader does not opt into prune support;
    # ``--prune-old`` then refuses with a clear error rather than
    # silently no-op'ing.
    entity_ids: list[str] = field(default_factory=list)


class ReferenceLoader(ABC):
    """Abstract base class for reference-data loader plugins.

    Concrete subclasses are distributed as ``hippo-reference-<name>``
    packages and registered via the ``hippo.reference_loaders`` entry
    point group. See spec §2.14 for lifecycle, caching, schema-fragment
    merge rules, and upgrade semantics.
    """

    name: str
    description: str

    # D2.14.A — optional Typer sub-app mounted under
    # ``hippo reference <name> ...``. Registered separately via the
    # ``hippo.reference_loader_cli`` entry point group.
    subcommands_app: typer.Typer | None = None

    # D2.14.D — optional Pydantic v2 model describing ``load()``
    # parameters. When declared, the CLI auto-renders ``--flag`` args
    # and validates user input before invoking ``load()``.
    load_params_schema: type[BaseModel] | None = None

    @abstractmethod
    def versions(self) -> list[str]:
        """Return the available version slugs for this loader.

        Slugs are opaque to Hippo (D2.14.C); format is loader-defined.
        Loaders SHOULD include ``"test"`` as a pseudo-version (D2.14.I).
        """

    @abstractmethod
    def entity_types(self) -> list[str]:
        """Return the entity type names this loader populates.

        Declarative only — for provenance and discoverability. Loader
        code owns the runtime ingestion order across these classes
        (Decision 9.5.F).
        """

    @abstractmethod
    def schema_fragment(self) -> dict:
        """Return a LinkML schema fragment defining this loader's
        entity types and relationships.

        Must declare ``default_prefix: <loader_name>:`` (D2.14.G,
        Rule 1).
        """

    @abstractmethod
    def load(
        self,
        client: HippoClient,
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Ingest the reference dataset at ``version`` into ``client``.

        ``params`` is an instance of ``load_params_schema`` if the
        subclass declares one, else ``None``.
        """

    def upgrade(
        self,
        client: HippoClient,
        from_version: str,
        to_version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Upgrade an installed loader from ``from_version`` to
        ``to_version`` (D2.14.F).

        Default implementation delegates to ``load(to_version, params)``.
        Subclasses with efficient diff logic should override.
        """
        return self.load(client, to_version, params)

    def validate(self, user_artifact: object) -> "ValidationResult":
        """Validate a user-supplied artifact against this loader's
        schema (D2.14.B).

        Recommended, not required. Default raises ``NotImplementedError``
        with the loader name in the message so CLI surfaces can render
        a clear "this loader does not implement validate()" hint.
        """
        raise NotImplementedError(f"{self.name} does not implement validate()")
