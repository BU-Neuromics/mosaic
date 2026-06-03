"""``Bundle`` meta-coordinate — a manifest pinning one coherent package set.

sec11 §11.6.2 / Doc 2 §3, §7. Hippo has no bundle concept today; this is
the first instantiation. The ``brainbank-bundle`` is the *illustrative*
proving case wired up in S5 — the bundle mechanism itself is
domain-neutral: any deployment with several inter-dependent
:class:`~hippo.core.loaders.schema_package.SchemaPackage`\\ s benefits from
pinning them as one coherent coordinate.

A bundle manifest pins each package to an exact version (the **target
coordinate**), optionally an ontology snapshot id (for reproducibility),
an optional bundle version, and an optional ordered list of **intermediate
coordinates** the orchestrator sequences through (each intermediate = one
dependency-ordered per-package evolve hop, sec11 §11.5.1).

The deployment's ``requires:`` block is **generated** from the manifest
(:meth:`to_requires`) rather than hand-maintained, so the pinned versions
always correspond to a known-coherent combination (sec11 §11.6.2).

Manifest shape (YAML)::

    name: brainbank-bundle
    version: "2024.1"              # optional
    ontology_snapshot: "2024-01"  # optional
    packages:                     # required: the target coordinate
      core: "2.0.0"
      subject: "1.4.0"
    coordinates:                  # optional: ordered intermediate hops
      - {core: "1.3.0"}
      - {core: "1.4.0"}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hippo.core.exceptions import ConfigError


@dataclass(frozen=True)
class Bundle:
    """A coherent, pinned ``(package → version)`` coordinate set.

    :attr:`packages` is the target coordinate. :attr:`coordinates` is an
    optional ordered list of intermediate coordinates the orchestrator
    steps through before the target (each a partial ``{name: version}``
    map); when empty, the orchestrator goes straight to the target in one
    dependency-ordered pass.
    """

    name: str
    packages: dict[str, str]
    ontology_snapshot: str | None = None
    version: str | None = None
    coordinates: tuple[dict[str, str], ...] = ()

    @classmethod
    def from_manifest(cls, source: str | Path | dict[str, Any]) -> "Bundle":
        """Parse a bundle manifest from a YAML file path or a parsed dict.

        Raises :class:`~hippo.core.exceptions.ConfigError` with a clear
        message on a malformed manifest (missing ``name`` / ``packages``,
        non-string version pins, etc.) so CLI surfaces render a precise hint.
        """
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise ConfigError(
                    f"bundle manifest not found: {path}", manifest=str(path)
                )
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = source
        if not isinstance(data, dict):
            raise ConfigError("bundle manifest must be a YAML mapping")

        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ConfigError("bundle manifest requires a string 'name'")

        packages = data.get("packages")
        if not isinstance(packages, dict) or not packages:
            raise ConfigError(
                f"bundle {name!r} requires a non-empty 'packages' mapping "
                f"of package → version",
                bundle=name,
            )
        pinned = cls._coerce_coordinate(name, "packages", packages)

        raw_coords = data.get("coordinates") or []
        if not isinstance(raw_coords, list):
            raise ConfigError(
                f"bundle {name!r}: 'coordinates' must be a list of "
                f"package → version mappings",
                bundle=name,
            )
        coordinates = tuple(
            cls._coerce_coordinate(name, f"coordinates[{i}]", coord)
            for i, coord in enumerate(raw_coords)
        )

        return cls(
            name=name,
            packages=pinned,
            ontology_snapshot=cls._coerce_optional_str(
                name, "ontology_snapshot", data.get("ontology_snapshot")
            ),
            version=cls._coerce_optional_str(name, "version", data.get("version")),
            coordinates=coordinates,
        )

    @staticmethod
    def _coerce_optional_str(
        bundle: str, field_name: str, value: Any
    ) -> str | None:
        """Validate an optional metadata field is a string when present.

        ``ontology_snapshot`` and ``version`` are optional, so ``None`` (the
        absent case) passes through. Anything else must be a string — a YAML
        ``version: 1.0`` parses to a float and would otherwise be stored
        silently, so we reject it the same way ``name`` is validated.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigError(
                f"bundle {bundle!r}: optional {field_name!r} must be a string "
                f"when present (got {value!r})",
                bundle=bundle,
            )
        return value

    @staticmethod
    def _coerce_coordinate(
        bundle: str, where: str, coord: Any
    ) -> dict[str, str]:
        if not isinstance(coord, dict) or not coord:
            raise ConfigError(
                f"bundle {bundle!r}: {where} must be a non-empty "
                f"package → version mapping",
                bundle=bundle,
            )
        out: dict[str, str] = {}
        for pkg, ver in coord.items():
            if not isinstance(pkg, str) or not isinstance(ver, str):
                raise ConfigError(
                    f"bundle {bundle!r}: {where} entry {pkg!r}: package and "
                    f"version must both be strings (got version {ver!r})",
                    bundle=bundle,
                )
            out[pkg] = ver
        return out

    def coordinate_sequence(self) -> list[dict[str, str]]:
        """The ordered hop sequence: intermediates then the target.

        Each element is a bundle coordinate the orchestrator drives the
        deployment to, in order (sec11 §11.5.1 — a coordinated multi-package
        upgrade sequences over intermediate bundle coordinates). The final
        element is always the target :attr:`packages`.
        """
        return [dict(c) for c in self.coordinates] + [dict(self.packages)]

    def to_requires(self) -> dict[str, str]:
        """Generate the ``requires:`` block for the deployment's user schema.

        Each pinned package becomes an exact (``==``) version requirement,
        matching hippo's ``requires: { <loader>: "==x.y.z" }`` pin gate
        (Doc 2 §1). Generated, not hand-maintained, so the deployment's pins
        always match this known-coherent bundle.
        """
        return {name: f"=={ver}" for name, ver in sorted(self.packages.items())}

    def requires_yaml(self) -> str:
        """Render the generated ``requires:`` block as a YAML snippet."""
        return yaml.safe_dump({"requires": self.to_requires()}, sort_keys=True)
