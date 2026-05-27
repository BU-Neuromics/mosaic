"""RecipeService - Recipe export, inspection, lineage, and bootstrap import facade.

Service facade following the same pattern as :class:`IngestionService`,
:class:`ProvenanceService`, and :class:`QueryService`. Composed once in
``HippoClient.__init__`` and exposed through thin ``client.recipe_<verb>``
wrappers.

Architecture invariants (sec10 §10.10) that this module preserves:

- (1) :class:`SchemaManager` owns schema merging — this service never
  touches ``SchemaView`` directly to merge.
- (2) All recipe schema writes flow through ``SchemaManager.merge_fragment(...)``.
- (3) Provenance is unconditional; every successful import emits exactly
  one ``recipe_imported`` event in the same transaction.

Phase 2 (PTS-290) shipped :meth:`__init__` + :meth:`list_installed`.
Phase 3 PR 5 (PTS-291) adds :meth:`inspect`. The remaining surface
(``import_``, ``export``, ``extend``, ``diff``, ``export_lockfile``,
``install_from_lockfile``) lands in subsequent PRs.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

import yaml

from hippo.core.exceptions import RecipeManifestError
from hippo.core.meta import get_meta
from hippo.core.recipe import (
    FileResolver,
    InstalledRecipe,
    RecipeAuthor,
    RecipeManifest,
    RecipeRef,
    RecipeReport,
    RecipeRequires,
    RecipeResolver,
    canonical_content_hash,
)
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter

if TYPE_CHECKING:
    from hippo.core.provenance_service import ProvenanceService
    from hippo.core.schema_manager import SchemaManager


META_KEY_INSTALLED_RECIPES = "installed_recipes"
"""``hippo_meta`` key under which installed-recipe records live.

Mirrors the ``reference_versions`` convention used by the Reference
Loader install/upgrade machinery (sec2 §2.14 step 5). The stored value
is a JSON object keyed by recipe ``id``; each entry conforms to
:class:`InstalledRecipe` (sec10 §10.3.4).
"""


_RECIPE_MANIFEST_SCHEMA_NAME = "recipe_manifest.yaml"


class _ManifestYAMLLoader(yaml.SafeLoader):
    """YAML loader that keeps ISO timestamps as strings.

    LinkML's ``datetime`` range serialises to a JSON Schema ``string``,
    so the bundled JSON-schema validator rejects a Python ``datetime``
    even when the value would round-trip cleanly. Stripping the
    timestamp implicit resolver leaves ISO 8601 instants as strings,
    which is what the manifest schema expects.
    """


_ManifestYAMLLoader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class RecipeService:
    """Recipe export, inspection, lineage, and bootstrap import.

    Delegates schema merging to :class:`SchemaManager` and provenance
    writes to :class:`ProvenanceService`. Reference Loader installs do
    NOT go through this service in v1.
    """

    def __init__(
        self,
        storage: Optional[SQLiteAdapter] = None,
        schema_manager: Optional["SchemaManager"] = None,
        provenance_service: Optional["ProvenanceService"] = None,
        *,
        cache_dir: Optional[Path] = None,
        resolvers: Optional[Sequence[RecipeResolver]] = None,
    ) -> None:
        """Compose the service.

        ``cache_dir`` is reserved for the HTTPS content-addressable
        cache that lands in PR 6 (PTS-291). ``resolvers`` defaults to
        ``[FileResolver()]`` when not supplied; the HTTPS resolver is
        appended automatically once the cache argument is wired in PR 6.
        """
        self._storage = storage
        self._schema_manager = schema_manager
        self._provenance_service = provenance_service
        self._cache_dir = cache_dir
        if resolvers is None:
            self._resolvers: tuple[RecipeResolver, ...] = (FileResolver(),)
        else:
            self._resolvers = tuple(resolvers)

    def list_installed(self) -> list[InstalledRecipe]:
        """Return every entry in ``hippo_meta.installed_recipes``.

        Returns ``[]`` on a clean instance, on adapters with no storage
        backing, or when the ``hippo_meta`` table predates the recipe
        subsystem (the key is simply absent).
        """
        if self._storage is None or not hasattr(self._storage, "_transaction"):
            return []
        with self._storage._transaction() as conn:
            payload = get_meta(conn, META_KEY_INSTALLED_RECIPES)
        if not payload:
            return []
        return [_installed_recipe_from_dict(entry) for entry in payload.values()]

    def inspect(
        self,
        source: str | Path,
        *,
        base_dir: Optional[Path] = None,
    ) -> RecipeReport:
        """Parse, validate, and digest a recipe without any state change (sec10 §10.2.3).

        Pipeline (sec10 §10.4): resolve ``source`` → read
        ``recipe.yaml`` → closed-schema validation against
        ``recipe_manifest.yaml`` → compute canonical content hash →
        enumerate the embedded ``schema.yaml``'s classes/slots. No DB
        writes. No cache writes. No provenance.

        Args:
            source: ``file:`` URI, ``https:`` URI, bare absolute path,
                or bare relative path. Tarballs are accepted.
            base_dir: Resolves bare relative paths and relative
                ``file:`` URIs. Defaults to ``Path.cwd()`` when
                ``source`` is a string and to ``source.parent`` when
                ``source`` is an existing ``Path`` (so callers passing
                a path-like get the natural local resolution behavior).

        Raises:
            RecipeManifestError: When the manifest fails closed-schema
                validation against ``recipe_manifest.yaml``.

        Notes:
            HTTPS sources work once :class:`HttpsResolver` lands in
            PR 6. Until then a ``ValueError`` from the resolver chain
            surfaces verbatim.
        """
        src_str = str(source)
        effective_base = base_dir
        if effective_base is None and isinstance(source, Path) and source.exists():
            effective_base = source.parent if source.is_file() else None

        resolver = self._select_resolver(src_str)
        with resolver.resolve(src_str, base_dir=effective_base) as recipe_dir:
            manifest_dict = self._read_manifest_yaml(recipe_dir, source=src_str)
            self._validate_manifest(manifest_dict, source=src_str)
            manifest = _manifest_from_dict(manifest_dict)
            digest = canonical_content_hash(recipe_dir)
            classes, slots = self._inspect_schema_elements(recipe_dir)

        return RecipeReport(
            manifest=manifest,
            digest=digest,
            classes=classes,
            slots=slots,
        )

    def _select_resolver(self, source: str) -> RecipeResolver:
        for r in self._resolvers:
            if r.can_handle(source):
                return r
        raise ValueError(
            f"No registered RecipeResolver handles source: {source!r}"
        )

    def _read_manifest_yaml(self, recipe_dir: Path, *, source: str) -> dict:
        manifest_path = recipe_dir / "recipe.yaml"
        if not manifest_path.is_file():
            raise RecipeManifestError(
                "Recipe is missing recipe.yaml at its root.",
                source=source,
            )
        try:
            data = yaml.load(
                manifest_path.read_text(encoding="utf-8"),
                Loader=_ManifestYAMLLoader,
            )
        except yaml.YAMLError as e:
            raise RecipeManifestError(
                f"Failed to parse recipe.yaml: {e}",
                source=source,
            ) from e
        if not isinstance(data, dict):
            raise RecipeManifestError(
                "recipe.yaml must be a YAML mapping at the top level.",
                source=source,
            )
        return data

    def _validate_manifest(self, manifest_dict: dict, *, source: str) -> None:
        """Closed-schema-validate ``manifest_dict`` against ``recipe_manifest.yaml``.

        Uses the bundled LinkML schema shipped under
        ``hippo.schemas`` and the same ``JsonschemaValidationPlugin(closed=True)``
        wiring exercised by the Phase-2 schema tests.
        """
        from linkml.validator import Validator
        from linkml.validator.plugins import JsonschemaValidationPlugin

        schema_path = importlib.resources.files("hippo.schemas").joinpath(
            _RECIPE_MANIFEST_SCHEMA_NAME
        )
        validator = Validator(
            schema=str(schema_path),
            validation_plugins=[JsonschemaValidationPlugin(closed=True)],
        )
        report = validator.validate(manifest_dict, "RecipeManifest")
        if report.results:
            messages = [r.message for r in report.results]
            raise RecipeManifestError(
                f"recipe.yaml failed validation ({len(messages)} error(s)): "
                f"{messages[0]}",
                source=source,
                recipe_id=manifest_dict.get("id"),
                recipe_version=manifest_dict.get("version"),
                errors=messages,
            )

    def _inspect_schema_elements(
        self,
        recipe_dir: Path,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return ``(classes, slots)`` declared in the recipe's ``schema.yaml``.

        ``inspect`` is read-only; no merge or LinkML SchemaView wiring
        happens here. When ``schema.yaml`` is absent or malformed, the
        report carries empty tuples — the merge layer (PR 7) is the
        gate that turns those into hard failures.
        """
        schema_path = recipe_dir / "schema.yaml"
        if not schema_path.is_file():
            return (), ()
        try:
            content = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return (), ()
        if not isinstance(content, dict):
            return (), ()

        classes = tuple(sorted((content.get("classes") or {}).keys()))
        slots = tuple(sorted((content.get("slots") or {}).keys()))
        return classes, slots


def _installed_recipe_from_dict(entry: dict) -> InstalledRecipe:
    """Hydrate one ``InstalledRecipe`` from its persisted JSON form.

    The persisted shape mirrors ``InstalledRecipe`` exactly (sec10 §10.3.4)
    plus an optional embedded ``parent`` ``RecipeRef``. Missing optional
    fields default per the dataclass.
    """
    parent_data = entry.get("parent")
    parent = None
    if parent_data is not None:
        parent = RecipeRef(
            id=parent_data["id"],
            version=parent_data["version"],
            source=parent_data["source"],
            digest=parent_data.get("digest"),
        )
    return InstalledRecipe(
        id=entry["id"],
        version=entry["version"],
        source=entry["source"],
        digest=entry["digest"],
        installed_at=entry["installed_at"],
        parent=parent,
    )


def _manifest_from_dict(data: dict) -> RecipeManifest:
    """Hydrate a :class:`RecipeManifest` from a closed-schema-validated dict.

    Optional sub-objects (``author``, ``parent``, ``requires``) are
    materialized into their typed counterparts. The caller is
    responsible for having validated ``data`` first — this function
    assumes the closed-schema contract holds.
    """
    author = None
    if (raw_author := data.get("author")) is not None:
        author = RecipeAuthor(
            name=raw_author.get("name"),
            email=raw_author.get("email"),
            organization=raw_author.get("organization"),
        )

    parent = None
    if (raw_parent := data.get("parent")) is not None:
        parent = RecipeRef(
            id=raw_parent["id"],
            version=raw_parent["version"],
            source=raw_parent["source"],
            digest=raw_parent.get("digest"),
        )

    requires_data = data.get("requires") or {}
    requires = RecipeRequires(
        recipes=tuple(
            RecipeRef(
                id=r["id"],
                version=r["version"],
                source=r["source"],
                digest=r.get("digest"),
            )
            for r in (requires_data.get("recipes") or [])
        ),
        reference_loaders=tuple(requires_data.get("reference_loaders") or []),
    )

    return RecipeManifest(
        id=data["id"],
        name=data["name"],
        version=data["version"],
        created_at=str(data["created_at"]),
        hippo_version=data["hippo_version"],
        description=data.get("description"),
        author=author,
        license=data.get("license"),
        source=data.get("source"),
        parent=parent,
        requires=requires,
    )
