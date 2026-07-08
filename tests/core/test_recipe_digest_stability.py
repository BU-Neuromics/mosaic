"""Digest stability across dir-form / tarball-form / repacking (sec10 §10.4.3).

PR 6 of PTS-291 — the acceptance test the issue calls out explicitly:

  Dir-form and tarball-form of the same recipe produce identical
  digests; tarball file-order does not affect digest.

These tests exercise ``FileResolver`` (extracts tarballs) +
``canonical_content_hash`` (digests the resulting directory). They do
not need ``HttpsResolver`` — the HTTPS path piggybacks on the same
extract-then-digest sequence.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from mosaic.core.recipe import FileResolver, canonical_content_hash


def _make_recipe(root: Path) -> Path:
    """Build a minimal recipe directory tree with deterministic contents."""
    d = root / "stable"
    d.mkdir()
    (d / "recipe.yaml").write_bytes(b"id: org.example.stable\n")
    (d / "schema.yaml").write_bytes(b"classes: {}\n")
    sub = d / "extra"
    sub.mkdir()
    (sub / "notes.md").write_bytes(b"hello\n")
    return d


def _pack_forward(recipe_dir: Path, out: Path) -> Path:
    """Pack files in the directory's natural iteration order."""
    with tarfile.open(out, "w:gz") as tf:
        tf.add(recipe_dir, arcname=recipe_dir.name)
    return out


def _pack_reverse(recipe_dir: Path, out: Path) -> Path:
    """Pack files in reverse-sorted order so the tarball's internal layout differs."""
    members = sorted(recipe_dir.rglob("*"), reverse=True)
    with tarfile.open(out, "w:gz") as tf:
        # Add the top-level dir entry first so extraction yields the
        # same root directory name as ``_pack_forward``.
        tf.add(recipe_dir, arcname=recipe_dir.name, recursive=False)
        for path in members:
            arcname = f"{recipe_dir.name}/{path.relative_to(recipe_dir).as_posix()}"
            tf.add(path, arcname=arcname, recursive=False)
    return out


class TestDigestStability:
    def test_dir_form_and_tarball_form_match(self, tmp_path: Path) -> None:
        recipe_dir = _make_recipe(tmp_path)
        tarball = _pack_forward(recipe_dir, tmp_path / "stable.tar.gz")

        dir_digest = canonical_content_hash(recipe_dir)
        with FileResolver().resolve(str(tarball)) as extracted:
            tar_digest = canonical_content_hash(extracted)

        assert dir_digest == tar_digest

    def test_tarball_file_order_does_not_affect_digest(
        self, tmp_path: Path
    ) -> None:
        recipe_dir = _make_recipe(tmp_path)
        forward = _pack_forward(recipe_dir, tmp_path / "f.tar.gz")
        reverse = _pack_reverse(recipe_dir, tmp_path / "r.tar.gz")

        # Sanity check the two tarballs really differ on disk; if they
        # don't, the test isn't proving anything.
        assert forward.read_bytes() != reverse.read_bytes()

        with FileResolver().resolve(str(forward)) as a:
            d_a = canonical_content_hash(a)
        with FileResolver().resolve(str(reverse)) as b:
            d_b = canonical_content_hash(b)

        assert d_a == d_b
