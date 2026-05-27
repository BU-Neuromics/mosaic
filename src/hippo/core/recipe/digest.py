"""Canonical-content-hash digest for a Hippo recipe (sec10 §10.4.3).

The digest is computed over a *canonical content hash* — not the
tarball bytes — so the same recipe shipped as a directory and as a
tarball yields identical digests and arbitrary repacking does not
shift the digest.

Algorithm (sec10 §10.4.3, handoff §"Digest algorithm"):

1. Enumerate every file in the recipe directory recursively, relative
   to the recipe root.
2. Sort the file list lexicographically by relative path (POSIX-style
   separators).
3. For each file in order, append to a single buffer:
       ``<relative-path-as-utf8>\\n<lowercase-hex-sha256-of-bytes>\\n``
4. The digest is ``sha256(buffer)``, lowercase hex.

No file is excluded — the recipe directory IS the recipe.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def canonical_content_hash(recipe_dir: Path) -> str:
    """Return the recipe's canonical content hash as lowercase hex (sec10 §10.4.3).

    The returned string is the raw 64-char sha256 hex. Call sites that
    want the ``sha256:`` prefix (e.g. for storage in ``RecipeRef.digest``)
    prepend it themselves.

    Raises ``NotADirectoryError`` if ``recipe_dir`` is not a directory —
    callers are responsible for tarball extraction (see ``FileResolver``).
    """
    if not recipe_dir.is_dir():
        raise NotADirectoryError(
            f"Recipe digest expects a directory, got: {recipe_dir}"
        )

    files = sorted(
        (p for p in recipe_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(recipe_dir).as_posix(),
    )

    outer = hashlib.sha256()
    for path in files:
        rel = path.relative_to(recipe_dir).as_posix()
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        outer.update(rel.encode("utf-8"))
        outer.update(b"\n")
        outer.update(file_hash.encode("ascii"))
        outer.update(b"\n")
    return outer.hexdigest()
