"""A realistic (non-``Fake``) ``ReferenceLoader`` exercising the full
external-data path: content-addressed ``cached_fetch``, sha256 integrity,
a diff-based ``upgrade``, the ``"test"`` network-free fixture, and the
``--prune-old`` write-log substrate (Doc 2 §1/§2A/§4, sec2 §2.14,
sec11 §11.2.3; PTS-337 S1).

Where :class:`~hippo.testing.fake_reference_loader.FakeReferenceLoader`
is a purely in-memory stub, ``OboDemoLoader`` simulates a real ontology
reference package (``hippo-reference-*``): it ships versioned releases as
content-addressed artifacts and ingests them as ``OntologyTerm`` rows.
It is bundled in ``hippo.testing`` (alongside ``fake``/``rich``/``bare``)
so the test suite has a concrete, hermetic species that drives the real
caching / fetch / diff machinery without a live network.

Identity model (why fresh ids, not stable CURIEs)
-------------------------------------------------
Each ontology term carries its source CURIE (``OBO:0000001``) as a *data
attribute* (:attr:`curie`); the Hippo entity ``id`` is server-generated
and **fresh** on every write. This is deliberate: with fresh ids a
release's rows are disjoint from the prior release's, so an additive
upgrade followed by ``--prune-old`` cleanly removes exactly the prior
version (sec2 §2.14.9 documents the stable-id overlap sharp edge that
fresh ids sidestep — see [[hippo-dev-env]] and the S2 prune tests).

Diff-based upgrade
------------------
"Via diff" is a property of the *fetch*, not of the write set (sec2
§2.14.4: "fetch only changed records"). A full release is a ``.obo``
file; an upgrade ships a small JSON *delta* (``added`` / ``changed`` /
``obsoleted``). :meth:`upgrade` re-reads the already-cached base release
(a cache hit — no re-download) and applies the delta to reconstruct the
full target term set, which it then ingests. The end state equals a full
``load(to_version)`` but the network cost is one small diff.

Reproducibility (Doc 2 §4)
--------------------------
Every fetchable artifact is pinned by sha256 in the bundled
``fixtures/obodemo/manifest.json``; :meth:`cached_fetch
<hippo.core.client.HippoClient.cached_fetch>` verifies the digest on
download and on cache hit, raising
:class:`~hippo.core.exceptions.CacheIntegrityError` on mismatch. The
schema-fragment merge auto-injects ``provided_by: obodemo@<version>`` on
the introduced classes/slots (sec2 §2.14.5 Rule 3).

Regenerating the manifest after editing a fixture (run from the repo root)::

    import hashlib, json, pathlib
    d = pathlib.Path("src/hippo/testing/fixtures/obodemo")
    m = json.loads((d / "manifest.json").read_text())
    for v, f in (("v1", "obodemo-v1.obo"), ("v2", "obodemo-v2.diff.json")):
        m[v]["sha256"] = hashlib.sha256((d / f).read_bytes()).hexdigest()
    (d / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
"""

from __future__ import annotations

import importlib.resources
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from hippo.core.loaders.reference import (
    EntityRef,
    LoadResult,
    ReferenceLoader,
)

if TYPE_CHECKING:
    from hippo.core.client import HippoClient

__all__ = ["OboDemoLoader", "OboDemoParams"]

# Reserved pseudo-version: a tiny, network-free bundled fixture for
# hermetic CI (sec2 §2.14.7).
_TEST_SLUG = "test"
_TEST_FIXTURE = "obodemo-test.obo"
_MANIFEST = "manifest.json"
_ENTITY_TYPE = "OntologyTerm"


class OboDemoParams(BaseModel):
    """Runtime parameters for :class:`OboDemoLoader`.

    Both fields render as CLI flags (``--base-url`` / ``--dry-run`` /
    ``--no-dry-run``) via the standard ``load_params_schema`` pipeline.
    """

    # Override the release origin. ``None`` (default) fetches from the
    # bundled fixtures via a ``file://`` URL, so the loader is hermetic
    # out of the box. Tests point this at an HTTP origin (to exercise the
    # network branch of ``cached_fetch``) or at a tampered directory (to
    # exercise the ``CacheIntegrityError`` branch).
    base_url: str | None = None
    # Preview an upgrade/load: reconstruct the target term set and
    # validate it against the merged schema *without writing any rows*
    # (the in-process equivalent of ``hippo ingest --validate-schema
    # --dry-run``, sec11 §11.5.2). A clean dry-run returns a ``LoadResult``
    # with ``errors == 0`` and the count it *would* have written.
    dry_run: bool = Field(default=False)


class OboDemoLoader(ReferenceLoader):
    """Example ontology reference loader (see module docstring)."""

    name = "obodemo"
    description = "Example OBO-style ontology reference loader (test fixture)"
    load_params_schema = OboDemoParams

    def versions(self) -> list[str]:
        # "test" first (reserved fixture); real releases follow.
        return [_TEST_SLUG, "v1", "v2"]

    def populates_types(self) -> list[str]:
        return [_ENTITY_TYPE]

    def schema_fragment(self) -> dict:
        return {
            "id": "https://example.org/hippo/obodemo",
            "name": "obodemo",
            "default_prefix": "obodemo",
            "prefixes": {"obodemo": "https://example.org/hippo/obodemo/"},
            "classes": {
                _ENTITY_TYPE: {
                    "is_a": "Entity",
                    "description": "A term from the obodemo example ontology.",
                    "attributes": {
                        # Source CURIE — the term's stable identity, kept
                        # as data (the Hippo entity id is fresh per write).
                        "curie": {"range": "string", "required": True},
                        "label": {"range": "string", "required": True},
                        "definition": {"range": "string"},
                    },
                },
            },
        }

    # ------------------------------------------------------------------
    # Lifecycle: load (provision) / upgrade (evolve, diff-based)
    # ------------------------------------------------------------------

    def load(
        self,
        client: "HippoClient",
        version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Ingest the full term set at ``version``.

        ``"test"`` reads the bundled tiny fixture directly (no network,
        no ``cached_fetch`` — sec2 §2.14.7 allows skipping the cache for
        small bundled files). ``"v1"`` fetches the full release through
        ``cached_fetch``. ``"v2"`` has no standalone full release; it is
        reconstructed from the cached ``v1`` base plus the bundled diff,
        so a fresh ``install obodemo --version v2`` and an
        ``upgrade v1 → v2`` converge on the same term set.
        """
        p = self._params(params)
        if version == _TEST_SLUG:
            terms = self._parse_obo(self._fixtures_dir() / _TEST_FIXTURE)
        elif version == "v1":
            terms = self._parse_obo(self._fetch(client, p, "v1"))
        elif version == "v2":
            terms = self._reconstruct_v2(client, p)
        else:
            return LoadResult(
                errors=1, error_messages=[f"unknown version: {version}"]
            )
        return self._ingest(client, terms, p)

    def upgrade(
        self,
        client: "HippoClient",
        from_version: str,
        to_version: str,
        params: BaseModel | None = None,
    ) -> LoadResult:
        """Diff-based upgrade — overrides the default full re-ingest.

        For the modeled ``v1 → v2`` hop, fetch only the small release
        diff (the ``v1`` base is re-read from the content-addressed cache
        — a hit, no re-download), reconstruct the full ``v2`` term set,
        and ingest it. Any other hop falls back to the genus default
        (full ``load(to_version)``).
        """
        p = self._params(params)
        if from_version == "v1" and to_version == "v2":
            terms = self._reconstruct_v2(client, p)
            return self._ingest(client, terms, p)
        return self.load(client, to_version, params)

    # ------------------------------------------------------------------
    # Fetch + parse helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _params(params: BaseModel | None) -> OboDemoParams:
        if isinstance(params, OboDemoParams):
            return params
        return OboDemoParams()

    def _fixtures_dir(self) -> Path:
        """Filesystem path to the bundled fixtures (package data)."""
        return Path(
            str(importlib.resources.files("hippo.testing.fixtures.obodemo"))
        )

    def _manifest(self) -> dict[str, Any]:
        raw = (self._fixtures_dir() / _MANIFEST).read_text(encoding="utf-8")
        return json.loads(raw)

    def _base_url(self, params: OboDemoParams) -> str:
        """Resolve the release origin as a slash-terminated URL.

        Defaults to the bundled fixtures via ``file://`` so the loader is
        hermetic; an explicit ``params.base_url`` (e.g. an HTTP origin)
        overrides it.
        """
        if params.base_url:
            return params.base_url.rstrip("/") + "/"
        return self._fixtures_dir().as_uri() + "/"

    def _fetch(
        self, client: "HippoClient", params: OboDemoParams, key: str
    ) -> Path:
        """Fetch artifact ``key`` from the manifest via ``cached_fetch``.

        sha256 is pinned in the manifest, so a content mismatch raises
        :class:`~hippo.core.exceptions.CacheIntegrityError`.
        """
        entry = self._manifest()[key]
        url = self._base_url(params) + entry["file"]
        return client.cached_fetch(
            url, expected_sha256=entry["sha256"], loader_name=self.name
        )

    def _reconstruct_v2(
        self, client: "HippoClient", params: OboDemoParams
    ) -> list[dict[str, Any]]:
        """Reconstruct the full ``v2`` term set from cached ``v1`` + diff."""
        base = self._parse_obo(self._fetch(client, params, "v1"))
        diff_path = self._fetch(client, params, "v2")
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        return self._apply_diff(base, diff)

    @staticmethod
    def _parse_obo(path: Path) -> list[dict[str, Any]]:
        """Minimal OBO ``[Term]`` stanza parser → term dicts.

        Recognises ``id`` (→ ``curie``), ``name`` (→ ``label``), and
        ``def`` (→ ``definition``, quote-stripped). Obsolete terms
        (``is_obsolete: true``) are dropped. Sufficient for the bundled
        fixtures; not a general-purpose OBO reader.
        """
        terms: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line == "[Term]":
                if current is not None:
                    terms.append(current)
                current = {}
                continue
            if current is None or not line or ":" not in line:
                continue
            tag, _, value = line.partition(":")
            tag = tag.strip()
            value = value.strip()
            if tag == "id":
                current["curie"] = value
            elif tag == "name":
                current["label"] = value
            elif tag == "def":
                # def: "text" [xrefs] — keep the quoted text only.
                if '"' in value:
                    current["definition"] = value.split('"')[1]
                else:
                    current["definition"] = value
            elif tag == "is_obsolete" and value.lower() == "true":
                current["_obsolete"] = True
        if current is not None:
            terms.append(current)
        return [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in terms
            if t.get("curie") and not t.get("_obsolete")
        ]

    @staticmethod
    def _apply_diff(
        base: list[dict[str, Any]], diff: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Apply a release delta to a base term set, keyed by CURIE.

        ``changed`` upserts, ``added`` inserts, ``obsoleted`` removes.
        Diff entries use the OBO field names (``id``/``name``/``def``);
        they are normalised to the ``curie``/``label``/``definition``
        shape used everywhere else.
        """

        def _normalise(entry: dict[str, Any]) -> dict[str, Any]:
            out: dict[str, Any] = {
                "curie": entry["id"],
                "label": entry["name"],
            }
            if entry.get("def") is not None:
                out["definition"] = entry["def"]
            return out

        by_curie = {t["curie"]: dict(t) for t in base}
        for entry in diff.get("changed", []):
            by_curie[entry["id"]] = _normalise(entry)
        for entry in diff.get("added", []):
            by_curie[entry["id"]] = _normalise(entry)
        for curie in diff.get("obsoleted", []):
            by_curie.pop(curie, None)
        # Deterministic order so write/validation output is stable.
        return [by_curie[c] for c in sorted(by_curie)]

    # ------------------------------------------------------------------
    # Ingest / dry-run gate
    # ------------------------------------------------------------------

    def _ingest(
        self,
        client: "HippoClient",
        terms: list[dict[str, Any]],
        params: OboDemoParams,
    ) -> LoadResult:
        """Write ``terms`` as fresh-id rows, or — in dry-run — validate
        them against the merged schema without writing.
        """
        if params.dry_run:
            errors = self._dry_run_validate(client, terms)
            return LoadResult(
                created=0 if errors else len(terms),
                errors=len(errors),
                error_messages=errors,
            )
        entities = [
            EntityRef.from_put_result(client.put(_ENTITY_TYPE, dict(term)))
            for term in terms
        ]
        return LoadResult(created=len(entities), entities=entities)

    def _dry_run_validate(
        self, client: "HippoClient", terms: list[dict[str, Any]]
    ) -> list[str]:
        """Stage ``terms`` into a tree-root bundle and dry-run-validate it
        against the client's merged registry (sec11 §11.5.2).

        Mirrors :meth:`DomainModule._run_gate` — builds the instance
        bundle, then calls :meth:`SchemaRegistry.validate`. Returns the
        list of error messages (empty == a clean dry-run). Ephemeral ids
        are assigned purely so the validator sees the required system
        fields; nothing is written.
        """
        registry = getattr(client, "registry", None)
        if registry is None:
            return [
                f"{self.name}: no merged schema registry available; "
                f"dry-run validation requires a schema-backed client."
            ]
        accessor_by_class = {
            slot.range: slot.name for slot in registry.tree_root_slots()
        }
        accessor = accessor_by_class.get(_ENTITY_TYPE)
        if accessor is None:
            return [
                f"{self.name}: class {_ENTITY_TYPE!r} has no tree-root "
                f"accessor in the merged schema (fragment not merged?)."
            ]
        bundle = {
            accessor: [
                {"id": str(uuid.uuid4()), "is_available": True, **term}
                for term in terms
            ]
        }
        return registry.validate(bundle, registry.tree_root_class_name())
