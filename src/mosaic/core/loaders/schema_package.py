"""``SchemaPackage`` genus ABC and capability protocols.

This module is the *spine* of the SchemaPackage refactor (Mosaic Migration
& Extension Design, Doc 2 §2A). It abstracts the reusable part of
:class:`~mosaic.core.loaders.reference.ReferenceLoader` — *"contribute a
versioned, pinnable schema fragment"* — into a base genus, leaving the
data behaviours (*"fetch & load external data"*, *"migrate first-party
data in place"*) to sibling species.

Genus / species split
----------------------
``SchemaPackage`` (genus)
    The pinnable contributor: ``name``, ``description``, ``versions()``,
    ``schema_fragment()`` (which must set ``default_prefix = name``; Mosaic
    auto-stamps ``provided_by`` at merge time), ``depends_on()``, an
    optional ``validate(artifact)``, and an optional ``load_params_schema``.
    The version-pin gate (``requires:`` + refuse-on-mismatch) and the
    three-layer merge precedence operate at *this* layer — they are about
    versioned fragments, not data. Three lifecycle hooks default to a
    **no-op** so a plain pure-schema package needs no hand-written code:
    ``provision``, ``evolve``, ``deprovision``.

Species (built incrementally across the sprint)
    - :class:`~mosaic.core.loaders.reference.ReferenceLoader` — external
      data; ``provision`` → ``load()``, ``evolve`` → ``upgrade()``,
      ``deprovision`` → prune. Keeps its historical method names so
      existing loaders are untouched (S0).
    - ``DomainModule`` — first-party mutable data; ``evolve`` is an
      in-place data migration (S2+).
    - Pure-schema modules (``core``, ``subject``, …) — a plain
      ``SchemaPackage`` with default no-op hooks; DDL handled by
      ``mosaic migrate``.

Capability **Protocols** (:class:`ExternalData`, :class:`MigratableData`)
carry typing + orchestrator dispatch, keeping the data behaviours
*siblings* rather than a deep inheritance chain — the hooks carry
behaviour, the protocols carry typing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import typer
from pydantic import BaseModel

if TYPE_CHECKING:
    from mosaic.core.client import MosaicClient
    from mosaic.core.loaders.reference import LoadResult
    from mosaic.core.validation.validators import ValidationResult


class SchemaPackage(ABC):
    """Genus: a versioned, pinnable contributor of a LinkML schema fragment.

    Concrete packages are distributed as Python distributions and
    registered via the ``mosaic.schema_packages`` entry-point group (with
    ``mosaic.reference_loaders`` as a subset/alias — see
    :func:`mosaic.core.loaders.discovery.discover_schema_packages`).

    A pure-schema package implements only the two abstract methods
    (:meth:`versions` and :meth:`schema_fragment`); the lifecycle hooks
    default to no-ops, so it merges and pins via ``requires:`` without any
    hand-written ``load()``. Data species override the hooks (see
    :class:`ExternalData` / :class:`MigratableData`).
    """

    #: Stable identifier; MUST equal ``schema_fragment()['default_prefix']``.
    name: str
    #: Human-readable one-liner surfaced by ``mosaic`` listings.
    description: str

    # Optional Typer sub-app mounted under ``mosaic reference <name> ...``
    # (D2.14.A). Registered separately via the
    # ``mosaic.reference_loader_cli`` entry-point group.
    subcommands_app: typer.Typer | None = None

    # Optional Pydantic v2 model describing ``provision``/``load`` params
    # (D2.14.D). When declared, the CLI auto-renders ``--flag`` args and
    # validates user input before invoking the lifecycle hook.
    load_params_schema: type[BaseModel] | None = None

    @abstractmethod
    def versions(self) -> list[str]:
        """Return the available version slugs for this package.

        Slugs are opaque to Mosaic (D2.14.C); format is package-defined.
        Packages SHOULD include ``"test"`` as a pseudo-version (D2.14.I).
        """

    @abstractmethod
    def schema_fragment(self) -> dict:
        """Return a LinkML schema fragment defining this package's
        classes / slots / relationships.

        Must declare ``default_prefix: <name>`` (D2.14.G, Rule 1). Mosaic
        auto-injects ``annotations.provided_by = <name>@<version>`` on
        every element the fragment introduces at merge time, so the
        fragment itself need not carry attribution.
        """

    def depends_on(self) -> list[str]:
        """Return the names of other :class:`SchemaPackage`\\ s this one
        depends on.

        Drives dependency-ordered merge + lifecycle orchestration (base
        before dependents). The default is no dependencies. Note this is
        the package-graph edge; cross-package foreign keys are not
        DB-validated in v1 (Doc 2 §1).
        """
        return []

    def validate(self, user_artifact: object) -> "ValidationResult":
        """Validate a user-supplied artifact against this package's schema
        (D2.14.B).

        Optional. The default raises ``NotImplementedError`` with the
        package name in the message so CLI surfaces can render a clear
        "this package does not implement validate()" hint.
        """
        raise NotImplementedError(f"{self.name} does not implement validate()")

    # ------------------------------------------------------------------
    # Lifecycle hooks — all default to a no-op (pure-schema packages).
    # Data species override these (or, for ReferenceLoader, map them onto
    # the historical load()/upgrade() method names). The orchestrator
    # dispatches uniformly across packages via these three names.
    # ------------------------------------------------------------------

    def provision(
        self,
        client: "MosaicClient",
        version: str,
        params: BaseModel | None = None,
    ) -> "LoadResult | None":
        """Install-time population. Default no-op (returns ``None``).

        Pure-schema packages contribute only DDL (handled by the merge +
        ``mosaic migrate``), so they leave this as the no-op.
        """
        return None

    def evolve(
        self,
        client: "MosaicClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = None,
    ) -> "LoadResult | None":
        """Upgrade-time transition from ``from_version`` to ``to_version``.

        Default no-op (returns ``None``). Migration-capable species
        (:class:`MigratableData`) override this and declare discrete,
        chain-aware migration steps; reference data re-ingests via the
        diff path.
        """
        return None

    def deprovision(
        self,
        client: "MosaicClient",
        version: str,
        *,
        force: bool = False,
    ) -> None:
        """Teardown. Default no-op (returns ``None``).

        A pure-schema package has no data rows, so the default ignores
        ``force`` and does nothing. Reference data leaves this no-op too —
        the orchestrator prunes its ``provided_by``-stamped rows off the
        ``reference_write_log`` substrate (the loader instance has no
        write-log handle). A :class:`~mosaic.core.loaders.domain_module.DomainModule`
        overrides this to **refuse by default** when it owns live records
        (sec11 §11.4.3); ``force=True`` acknowledges the soft-delete.
        """
        return None


@runtime_checkable
class ExternalData(Protocol):
    """Capability protocol: a :class:`SchemaPackage` that fetches and loads
    externally-maintained data.

    Satisfied by :class:`~mosaic.core.loaders.reference.ReferenceLoader`,
    which exposes ``load()`` / ``upgrade()``. The genus deliberately does
    *not* define those names, so only the external-data species matches
    this protocol — letting the orchestrator dispatch
    ``isinstance(pkg, ExternalData)`` cleanly.
    """

    def load(
        self,
        client: "MosaicClient",
        version: str,
        params: BaseModel | None = ...,
    ) -> "LoadResult": ...

    def upgrade(
        self,
        client: "MosaicClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = ...,
    ) -> "LoadResult": ...


@runtime_checkable
class MigratableData(Protocol):
    """Capability protocol: a :class:`SchemaPackage` that owns mutable data
    and migrates it in place across versions.

    The discriminating member is :meth:`migration_steps` — the declared
    migration DAG (Doc 2 §2A). The genus ships a no-op ``evolve``, so a
    protocol keyed on ``evolve`` alone would match *every* package;
    keying on ``migration_steps`` matches only the migration-capable
    species. No class satisfies this protocol in S0 — ``DomainModule``
    (S2) is the first implementor; the return shape of the step
    collection is pinned down in S3.
    """

    def migration_steps(self) -> list: ...

    def evolve(
        self,
        client: "MosaicClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = ...,
    ) -> "LoadResult | None": ...
