"""Tests for the canonical-content-hash digest (sec10 §10.4.3).

PR 5 of PTS-291 — the digest algorithm. PR 6 extends the surface with
tarball-form / directory-form parity (both forms produce the same
digest); that test moves with the resolver tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mosaic.core.recipe import canonical_content_hash


def _write(recipe_dir: Path, files: dict[str, bytes]) -> None:
    for rel, body in files.items():
        target = recipe_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)


class TestDigestBasics:
    def test_digest_is_lowercase_hex(self, tmp_path: Path) -> None:
        _write(tmp_path, {"recipe.yaml": b"id: x\n", "schema.yaml": b"classes: {}\n"})
        digest = canonical_content_hash(tmp_path)
        assert len(digest) == 64
        int(digest, 16)
        assert digest == digest.lower()

    def test_digest_changes_with_content(self, tmp_path: Path) -> None:
        _write(tmp_path, {"recipe.yaml": b"id: a\n"})
        d1 = canonical_content_hash(tmp_path)
        (tmp_path / "recipe.yaml").write_bytes(b"id: b\n")
        d2 = canonical_content_hash(tmp_path)
        assert d1 != d2

    def test_digest_changes_with_filename(self, tmp_path: Path) -> None:
        _write(tmp_path, {"recipe.yaml": b"x"})
        d1 = canonical_content_hash(tmp_path)
        (tmp_path / "recipe.yaml").rename(tmp_path / "recipe-2.yaml")
        d2 = canonical_content_hash(tmp_path)
        assert d1 != d2


class TestDigestAlgorithm:
    def test_matches_documented_formula(self, tmp_path: Path) -> None:
        _write(tmp_path, {"recipe.yaml": b"hello", "schema.yaml": b"world"})

        expected = hashlib.sha256()
        for rel, body in sorted(
            [("recipe.yaml", b"hello"), ("schema.yaml", b"world")]
        ):
            inner = hashlib.sha256(body).hexdigest()
            expected.update(rel.encode("utf-8"))
            expected.update(b"\n")
            expected.update(inner.encode("ascii"))
            expected.update(b"\n")
        assert canonical_content_hash(tmp_path) == expected.hexdigest()

    def test_nested_paths_use_posix_separators(self, tmp_path: Path) -> None:
        """Nested file paths are joined with ``/`` regardless of platform."""
        _write(tmp_path, {"subdir/file.yaml": b"x"})

        expected = hashlib.sha256()
        inner = hashlib.sha256(b"x").hexdigest()
        expected.update(b"subdir/file.yaml\n")
        expected.update(inner.encode("ascii"))
        expected.update(b"\n")
        assert canonical_content_hash(tmp_path) == expected.hexdigest()


class TestDigestSortOrder:
    """Files are hashed in lexicographic order regardless of creation order."""

    def test_creation_order_does_not_matter(self, tmp_path: Path) -> None:
        # Create in reverse order; digest must equal forward order.
        (tmp_path / "z.yaml").write_bytes(b"Z")
        (tmp_path / "a.yaml").write_bytes(b"A")
        d1 = canonical_content_hash(tmp_path)

        # Tear down and rebuild in forward order.
        (tmp_path / "z.yaml").unlink()
        (tmp_path / "a.yaml").unlink()
        (tmp_path / "a.yaml").write_bytes(b"A")
        (tmp_path / "z.yaml").write_bytes(b"Z")
        d2 = canonical_content_hash(tmp_path)
        assert d1 == d2


class TestDigestErrors:
    def test_non_directory_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "not-a-dir.txt"
        f.write_bytes(b"x")
        with pytest.raises(NotADirectoryError):
            canonical_content_hash(f)
