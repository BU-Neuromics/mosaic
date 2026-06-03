"""``DomainModule`` species and single-hop ``evolve`` (Doc 2 §2A, sec11 §11.2.4).

``DomainModule`` is the *first-party mutable-data* species of the
:class:`~hippo.core.loaders.schema_package.SchemaPackage` genus. Where
:class:`~hippo.core.loaders.reference.ReferenceLoader` wraps externally
maintained, reconstructible reference datasets, a ``DomainModule`` owns
the deployment's **locally authored, operational** records — the lab's
authoritative domain data — and migrates them *in place* across versions.

It satisfies the :class:`~hippo.core.loaders.schema_package.MigratableData`
capability protocol via two members:

* :meth:`DomainModule.migration_steps` — the declared migration edges.
* :meth:`DomainModule.evolve` — runs the single declared
  ``(from_version → to_version)`` step (S2 scope).

Semantic transformation model (sec11 §11.3, Doc 2 §5.2)
-------------------------------------------------------
A migration step is a small, independently testable transform that
**reads old-shape records, writes new-shape records, and supersedes the
old**. Each migrated record becomes a *new* entity (fresh id) and the
old entity is marked superseded by it (``supersede_entity``), so:

* the append-only, id-keyed, provenanced substrate makes the migration
  auditable and replay-recoverable (Doc 2 §2 rationale);
* every step emits ``supersede`` provenance events + a ``superseded_by``
  relationship edge ⇒ traceable lineage.

A consequence worth recording: after a migration, anything that
referenced an ``old_id`` now points at a superseded / unavailable
entity; resolution is via the ``superseded_by`` edge. This does not
surface in a single-class S2 proof, but S3 (multi-hop) and S4
(cross-package orchestration) inherit it.

Hard validation gate (sec11 §11.5.2, Doc 2 §5.4)
------------------------------------------------
The transform output is **staged** and dry-run-validated against the
fully merged schema *before any committed write*; the migration commits
only on green. In-process this reuses the same primitive the
``hippo ingest --validate-schema <merged-dir> --dry-run`` CLI path
calls — :meth:`SchemaRegistry.validate` against the merged registry the
client already operates on (:attr:`HippoClient.registry`). Only the
*new* records are validated; the old superseded rows are v1-shape and
are never re-validated.

Scope note (S2)
---------------
This module implements the **single-hop** evolve: one declared edge,
resolved by exact ``(from_version, to_version)`` match. Multi-hop
path-finding over the DAG (intermediate-step composition, shortcut
edges, the below-floor fail-loud), ``deprovision`` refuse-by-default +
dependents guard, and mid-commit rollback atomicity are explicitly S3/S4
(sec11 §11.7.2). :class:`MigrationStep` is deliberately a bare DAG edge
so the S3 resolver composes it without a rewrite.
"""

from __future__ import annotations

import tempfile
import uuid
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import yaml
from pydantic import BaseModel

from hippo.core.exceptions import MigrationGateError, MigrationStepNotFoundError
from hippo.core.loaders.reference import EntityRef, LoadResult
from hippo.core.loaders.schema_package import SchemaPackage

if TYPE_CHECKING:
    from hippo.core.client import HippoClient
    from hippo.linkml_bridge import SchemaRegistry

__all__ = [
    "DomainModule",
    "MigrationStep",
    "MigrationContext",
    "MigrationPlan",
    "StagedWrite",
    "StagedSupersession",
]


@dataclass(frozen=True)
class StagedWrite:
    """A new-shape record staged by a migration transform, not yet committed.

    ``data`` always carries an ``id`` (assigned by :meth:`MigrationPlan.migrate`
    when the transform does not supply one) so the staged bundle is concrete
    and the matching supersession can reference it.
    """

    entity_type: str
    data: dict


@dataclass(frozen=True)
class StagedSupersession:
    """A pending ``old_id → new_id`` supersession staged by a transform.

    Committed via :meth:`HippoClient.supersede_entity` *after* the gate
    passes and the new record exists, so both endpoints resolve.
    """

    old_id: str
    new_id: str
    reason: str | None = None


class MigrationPlan:
    """Accumulator for one ``evolve`` hop — nothing is committed until the gate passes.

    A migration transform reads old records from the client and records
    its intended new-shape writes / supersessions here. :meth:`DomainModule.evolve`
    then stages the writes, runs the dry-run validation gate, and only on
    green replays the plan against the client.

    The common 1:1 case is :meth:`migrate`. :meth:`put` (net-new record,
    no supersession) and :meth:`supersede` (explicit edge) cover splits,
    merges, and hand-tuned lineage.
    """

    def __init__(self) -> None:
        self._writes: list[StagedWrite] = []
        self._supersessions: list[StagedSupersession] = []

    @property
    def writes(self) -> list[StagedWrite]:
        """New-shape records staged for write, in declaration order."""
        return list(self._writes)

    @property
    def supersessions(self) -> list[StagedSupersession]:
        """Pending ``old_id → new_id`` supersessions, in declaration order."""
        return list(self._supersessions)

    def migrate(
        self,
        entity_type: str,
        old_id: str,
        new_data: dict,
        reason: str | None = None,
    ) -> str:
        """Stage a new-shape record that **supersedes** ``old_id`` (1:1 migration).

        Always creates a *new* entity: any ``id`` in ``new_data`` is
        replaced with a fresh UUID, because :meth:`HippoClient.supersede_entity`
        requires two distinct entities and emits the ``supersede`` event
        (an in-place same-id upsert would emit ``update`` instead — not a
        migration lineage). Returns the new entity's id.

        System fields (``id``, ``is_available``) are filled in so authors
        write only domain slots; ``is_available`` defaults to ``True`` (a
        migration produces live records) unless ``new_data`` sets it.
        """
        new_id = str(uuid.uuid4())
        record = {"is_available": True, **new_data, "id": new_id}
        self._writes.append(StagedWrite(entity_type=entity_type, data=record))
        self._supersessions.append(
            StagedSupersession(old_id=old_id, new_id=new_id, reason=reason)
        )
        return new_id

    def put(self, entity_type: str, new_data: dict) -> str:
        """Stage a net-new record with no supersession (e.g. one half of a split).

        Assigns a fresh UUID when ``new_data`` has no ``id`` and defaults
        ``is_available`` to ``True``. Returns the record's id so callers
        can wire an explicit :meth:`supersede`.
        """
        new_id = new_data.get("id") or str(uuid.uuid4())
        record = {"is_available": True, **new_data, "id": new_id}
        self._writes.append(StagedWrite(entity_type=entity_type, data=record))
        return new_id

    def supersede(
        self, old_id: str, new_id: str, reason: str | None = None
    ) -> None:
        """Stage an explicit ``old_id → new_id`` supersession edge.

        Pairs with :meth:`put` for non-1:1 migrations (a split where two
        new records jointly supersede one old record, etc.).
        """
        self._supersessions.append(
            StagedSupersession(old_id=old_id, new_id=new_id, reason=reason)
        )

    def is_empty(self) -> bool:
        """True when the transform staged neither writes nor supersessions."""
        return not self._writes and not self._supersessions


@dataclass
class MigrationContext:
    """Everything a migration transform receives for one hop.

    Read old-shape records via ``ctx.client`` (e.g.
    ``ctx.client.query(type).items``) and stage new-shape records via
    ``ctx.plan`` (:meth:`MigrationPlan.migrate` / ``put`` / ``supersede``).
    The transform must **not** write to the client directly — staging
    keeps the dry-run gate ahead of every committed write.
    """

    client: "HippoClient"
    from_version: str
    to_version: str
    plan: MigrationPlan
    params: BaseModel | None = None


@dataclass(frozen=True)
class MigrationStep:
    """One declared migration edge: a ``(from_version → to_version)`` transform.

    ``transform`` reads old records and stages new-shape records +
    supersessions onto ``ctx.plan``. Steps are bare DAG edges by design:
    the S3 resolver composes them into multi-hop paths (with shortcut
    edges and a floor) without changing this shape.
    """

    from_version: str
    to_version: str
    transform: Callable[[MigrationContext], None]
    description: str = ""


class DomainModule(SchemaPackage):
    """First-party, mutable-data species of :class:`SchemaPackage`.

    Owns the deployment's locally authored operational records and
    migrates them in place. Authors implement :meth:`schema_fragment` and
    :meth:`versions` (from the genus) plus :meth:`migration_steps`; the
    genus ``provision`` / ``deprovision`` no-ops are inherited (domain
    data arrives via ``hippo ingest``, not at schema-install time).

    Satisfies the :class:`~hippo.core.loaders.schema_package.MigratableData`
    protocol (``migration_steps`` + ``evolve``).
    """

    @abstractmethod
    def migration_steps(self) -> list[MigrationStep]:
        """Return every declared migration edge shipped with this module.

        All steps covering the module's supported range ship with the
        module at its current version (sec11 §11.3.2) — the resolver
        never fetches old module code. S2 uses these as a flat set of
        single-hop edges; S3 reads the same list as a DAG.
        """

    def populates_types(self) -> list[str]:
        """Entity-type names this module fills with first-party data.

        A species concern (parallel to
        :meth:`ReferenceLoader.populates_types`): declarative, for
        provenance and discoverability. Defaults to empty; authors that
        want richer reporting override it.
        """
        return []

    # ------------------------------------------------------------------
    # MigratableData: single-hop evolve (S2). provision/deprovision are
    # inherited genus no-ops. NOTE: deprovision refuse-by-default + the
    # dependents guard (sec11 §11.4.3) are explicitly S3 — left as the
    # genus no-op here so S2 does not pre-empt that design.
    # ------------------------------------------------------------------

    def evolve(
        self,
        client: "HippoClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Run the declared ``(from_version → to_version)`` migration step.

        1. Resolve the single declared step by exact match (single-hop;
           S3 generalizes to multi-hop path-finding).
        2. Run its transform → stage new-shape records + supersessions
           onto a :class:`MigrationPlan` (no writes yet).
        3. **Gate:** stage the new records and dry-run-validate them
           against the merged schema (:meth:`_run_gate`). On failure raise
           :class:`MigrationGateError` and commit nothing.
        4. **Commit (green only):** write the new records, then supersede
           the old ones — order matters so both endpoints exist when
           :meth:`HippoClient.supersede_entity` runs. Each supersession
           is tagged ``actor=<module name>`` / ``reason=<from→to>`` so the
           provenance reads as a migration, not a hand edit.

        Returns a :class:`LoadResult` where ``created`` counts the
        new-shape records written; the matching old records are
        superseded (1:1 for :meth:`MigrationPlan.migrate`).
        """
        step = self._resolve_step(from_version, to_version)

        plan = MigrationPlan()
        context = MigrationContext(
            client=client,
            from_version=from_version,
            to_version=to_version,
            plan=plan,
            params=params,
        )
        step.transform(context)

        # Hard validation gate — BEFORE any committed write.
        self._run_gate(client, from_version, to_version, plan)

        # Commit. New records first so supersede_entity's replacement exists.
        result = LoadResult()
        default_reason = f"{self.name} migration {from_version}→{to_version}"
        for write in plan.writes:
            rec = client.put(
                write.entity_type, write.data, entity_id=write.data.get("id")
            )
            result.created += 1
            result.entities.append(
                EntityRef(
                    id=rec.get("id") or write.data["id"],
                    type=write.entity_type,
                )
            )
        for sup in plan.supersessions:
            client.supersede_entity(
                sup.old_id,
                sup.new_id,
                reason=sup.reason or default_reason,
                actor=self.name,
            )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_step(
        self, from_version: str, to_version: str
    ) -> MigrationStep:
        """Find the single declared step for ``(from_version, to_version)``.

        Exact-match, single-hop (S2). Fails loud via
        :class:`MigrationStepNotFoundError` when zero or more than one
        step matches — no silent no-op, no guessing a path.
        """
        steps = self.migration_steps()
        matches = [
            s
            for s in steps
            if s.from_version == from_version and s.to_version == to_version
        ]
        available = [(s.from_version, s.to_version) for s in steps]
        if not matches:
            raise MigrationStepNotFoundError(
                message=(
                    f"{self.name}: no migration step declared for "
                    f"{from_version}→{to_version}. Multi-hop chaining "
                    f"is S3; declare a direct step or upgrade one hop at a time."
                ),
                package=self.name,
                from_version=from_version,
                to_version=to_version,
                available_steps=available,
            )
        if len(matches) > 1:
            raise MigrationStepNotFoundError(
                message=(
                    f"{self.name}: {len(matches)} migration steps declared for "
                    f"{from_version}→{to_version}; a hop must be unique."
                ),
                package=self.name,
                from_version=from_version,
                to_version=to_version,
                available_steps=available,
            )
        return matches[0]

    def _run_gate(
        self,
        client: "HippoClient",
        from_version: str,
        to_version: str,
        plan: MigrationPlan,
    ) -> None:
        """Stage the plan's new records and dry-run-validate the merged schema.

        Mirrors ``hippo ingest --validate-schema <merged-dir> --dry-run``
        in-process: builds a tree-root instance bundle from the staged
        writes, serializes it to a staging file (so the operation is
        literally *stage output → dry-run*), parses it back, and validates
        against the client's merged registry. Raises
        :class:`MigrationGateError` on any validation error — caller
        commits nothing.

        A plan with no staged writes validates trivially (an empty bundle
        is a no-op migration).
        """
        registry = client.registry
        if registry is None:
            raise MigrationGateError(
                message=(
                    f"{self.name}: cannot run the migration validation gate — "
                    f"the client has no merged schema registry. A domain "
                    f"migration must run against a schema-backed client."
                ),
                package=self.name,
                from_version=from_version,
                to_version=to_version,
            )

        bundle = self._build_bundle(registry, from_version, to_version, plan)

        with tempfile.TemporaryDirectory(prefix="hippo-migrate-") as tmp:
            staged = Path(tmp) / "staged.yaml"
            staged.write_text(yaml.safe_dump(bundle), encoding="utf-8")
            parsed = yaml.safe_load(staged.read_text(encoding="utf-8")) or {}

        errors = registry.validate(parsed, registry.tree_root_class_name())
        if errors:
            raise MigrationGateError(
                message=(
                    f"{self.name}: staged {from_version}→{to_version} "
                    f"migration failed the schema gate "
                    f"({len(errors)} error(s)); nothing was written."
                ),
                package=self.name,
                from_version=from_version,
                to_version=to_version,
                errors=list(errors),
            )

    def _build_bundle(
        self,
        registry: "SchemaRegistry",
        from_version: str,
        to_version: str,
        plan: MigrationPlan,
    ) -> dict:
        """Group staged writes into a tree-root instance bundle by accessor slot.

        The merged registry maps each concrete class to its tree-root
        accessor slot (``Sample`` → ``samples``). A staged write whose
        ``entity_type`` is not a class in the merged schema is itself a
        gate failure (the new shape names a class the schema does not
        define), surfaced as :class:`MigrationGateError`.
        """
        accessor_by_class = {
            slot.range: slot.name for slot in registry.tree_root_slots()
        }
        bundle: dict[str, list[dict]] = {}
        for write in plan.writes:
            accessor = accessor_by_class.get(write.entity_type)
            if accessor is None:
                raise MigrationGateError(
                    message=(
                        f"{self.name}: staged record class {write.entity_type!r} "
                        f"has no tree-root accessor in the merged schema; the "
                        f"new shape references an undefined class."
                    ),
                    package=self.name,
                    from_version=from_version,
                    to_version=to_version,
                    errors=[f"unknown class {write.entity_type!r}"],
                )
            bundle.setdefault(accessor, []).append(write.data)
        return bundle
