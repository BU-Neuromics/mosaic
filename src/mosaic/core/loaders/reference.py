"""``ReferenceLoader`` species, ``LoadResult``, and ``EntityRef``.

``ReferenceLoader`` is the *external-data* species of the
:class:`~mosaic.core.loaders.schema_package.SchemaPackage` genus (Mosaic
Migration & Extension Design, Doc 2 §2A). It is the surface for
reference-data plugins (e.g. ``mosaic-reference-fma``,
``mosaic-reference-ensembl``). The contract is fixed by Mosaic design
spec §2.14 (`hippo/design/sec2_architecture.md`) and decisions D2.14.A–I
in `hippo/design/sec9_decisions.md`.

The genus contributes the pinnable-fragment machinery (``versions()``,
``schema_fragment()``, ``depends_on()``, ``validate()``, the
``provision``/``evolve``/``deprovision`` lifecycle hooks). This module
adds the external-data behaviour: ``load()`` / ``upgrade()`` keep their
historical names so existing loaders are untouched, and the genus hooks
are mapped onto them (``provision`` → ``load``, ``evolve`` → ``upgrade``)
so the orchestrator can dispatch uniformly.

:class:`SchemaPackage` (and the capability protocols) are re-exported
here for convenience, since loaders already import from this module.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

from mosaic.core.loaders.schema_package import (
    ExternalData,
    MigratableData,
    SchemaPackage,
)

if TYPE_CHECKING:
    from mosaic.core.client import MosaicClient

__all__ = [
    "EntityRef",
    "LoadResult",
    "ReferenceLoader",
    "SchemaPackage",
    "ExternalData",
    "MigratableData",
]


@dataclass(frozen=True)
class EntityRef:
    """Lightweight ``(id, type)`` handle to a written entity.

    Accumulated into :attr:`LoadResult.entities` so multi-class loaders
    can report heterogeneous writes without an iterable return type.
    Advisory — not load-bearing for ``--prune-old`` (the reference write
    log is the authoritative substrate per spec §2.14.9 / D2.14.J).
    """

    id: str
    type: str

    @classmethod
    def from_put_result(cls, rec: dict) -> "EntityRef":
        """Bridge from the dict returned by :meth:`MosaicClient.put` to an
        :class:`EntityRef`.

        Use inside ``load()`` when assembling :attr:`LoadResult.entities`
        for the advisory inspection list.
        """
        return cls(id=rec["id"], type=rec["entity_type"])


@dataclass
class LoadResult:
    """Outcome of a single :meth:`ReferenceLoader.load` or
    :meth:`ReferenceLoader.upgrade` invocation.

    Counters answer "what happened"; :attr:`entities` answers "what was
    written" and is advisory only (spec §2.14.8 / D2.14.K).
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    # Advisory inspection list (spec §2.14.8). Loaders MAY populate it
    # for CLI breakdown / tests; consumers MUST NOT treat it as
    # authoritative — large loaders are encouraged to leave it empty and
    # let the reference write log carry the prune substrate.
    entities: list[EntityRef] = field(default_factory=list)


class ReferenceLoader(SchemaPackage):
    """External-data species of :class:`SchemaPackage`.

    Concrete subclasses are distributed as ``mosaic-reference-<name>``
    packages and registered via the ``mosaic.reference_loaders`` entry
    point group (a subset/alias of ``mosaic.schema_packages``). See spec
    §2.14 for lifecycle, caching, schema-fragment merge rules, and
    upgrade semantics.

    Inherits ``name``, ``description``, ``versions()``,
    ``schema_fragment()``, ``depends_on()``, ``validate()``,
    ``load_params_schema`` and ``subcommands_app`` from the genus. Adds
    the external-data behaviour: ``load()`` (abstract) and ``upgrade()``,
    and maps the genus lifecycle hooks onto them.
    """

    @abstractmethod
    def load(
        self,
        client: "MosaicClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Ingest the reference dataset at ``version`` into ``client``.

        ``params`` is an instance of ``load_params_schema`` if the
        subclass declares one, else ``None``.
        """

    def upgrade(
        self,
        client: "MosaicClient",
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

    def populates_types(self) -> list[str]:
        """Return the entity-type names this loader fills with *data*.

        A *species* concern (Doc 2 §2A): distinct from the types a
        package *defines* via :meth:`schema_fragment`. Declarative only —
        for provenance and discoverability; loader code owns the runtime
        ingestion order across these classes (Decision 9.5.F).

        Renamed from ``entity_types()``. For back-compat the default
        delegates to :meth:`entity_types`, so loaders written against the
        pre-``SchemaPackage`` ABC (which override ``entity_types()``)
        keep reporting their declared types unchanged. New loaders should
        override this method directly.
        """
        return self.entity_types()

    def entity_types(self) -> list[str]:
        """Deprecated alias for :meth:`populates_types`.

        Retained so loaders written against the pre-``SchemaPackage`` ABC
        — which declared ``entity_types()`` as an abstract method — keep
        instantiating and reporting their declared types unchanged. New
        loaders should override :meth:`populates_types` instead. Returns
        an empty list by default.
        """
        return []

    # ------------------------------------------------------------------
    # Genus lifecycle hooks mapped onto the historical method names, so
    # the orchestrator can dispatch provision/evolve/deprovision while
    # loader authors keep load()/upgrade() (Doc 2 §2A back-compat).
    # ------------------------------------------------------------------

    def provision(
        self,
        client: "MosaicClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Install-time population → :meth:`load`."""
        return self.load(client, version, params)

    def evolve(
        self,
        client: "MosaicClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Upgrade-time transition → :meth:`upgrade` (re-ingest / diff)."""
        return self.upgrade(client, from_version, to_version, params)

    # ``deprovision`` → prune is driven by the orchestrator off the
    # ``reference_write_log`` substrate (D2.14.J), not by the loader
    # instance (which has no handle to the write log). The genus no-op is
    # inherited here so the orchestrator stays the single owner of the
    # prune; reference loaders do not override it.
