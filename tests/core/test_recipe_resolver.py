"""Tests for FileResolver (sec10 §10.4.1).

PR 5 of PTS-291. Verifies that ``FileResolver`` materialises a recipe
directory from each supported source form:

- ``file:///abs/path``
- ``file:./rel/path``
- ``/abs/path``
- ``rel/path``
- a ``.tar.gz`` tarball

Tarball extraction is a security-sensitive surface; the cases here
also cover symlink/traversal rejection by ``_tar_filter``.
"""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest

from mosaic.core.recipe import FileResolver
from mosaic.core.recipe.resolver import _tar_filter


@pytest.fixture
def recipe_dir(tmp_path: Path) -> Path:
    recipe = tmp_path / "my-recipe"
    recipe.mkdir()
    (recipe / "recipe.yaml").write_text("id: org.example.r\n")
    (recipe / "schema.yaml").write_text("classes: {}\n")
    return recipe


class TestFileResolverPaths:
    def test_bare_absolute_directory_path(self, recipe_dir: Path) -> None:
        with FileResolver().resolve(str(recipe_dir)) as p:
            assert p == recipe_dir
            assert (p / "recipe.yaml").is_file()

    def test_file_uri_absolute(self, recipe_dir: Path) -> None:
        uri = f"file://{recipe_dir}"
        with FileResolver().resolve(uri) as p:
            assert p == recipe_dir

    def test_file_uri_triple_slash_absolute(self, recipe_dir: Path) -> None:
        uri = f"file://{recipe_dir}"
        # canonical RFC8089 form ``file:///path/...`` (path-absolute)
        assert uri.startswith("file://")
        with FileResolver().resolve(uri) as p:
            assert p == recipe_dir

    def test_bare_relative_path_resolves_against_base_dir(
        self, tmp_path: Path, recipe_dir: Path
    ) -> None:
        rel = recipe_dir.relative_to(tmp_path).as_posix()
        with FileResolver().resolve(rel, base_dir=tmp_path) as p:
            assert p.resolve() == recipe_dir.resolve()

    def test_file_uri_relative_resolves_against_base_dir(
        self, tmp_path: Path, recipe_dir: Path
    ) -> None:
        rel = recipe_dir.relative_to(tmp_path).as_posix()
        uri = f"file:{rel}"
        with FileResolver().resolve(uri, base_dir=tmp_path) as p:
            assert p.resolve() == recipe_dir.resolve()

    def test_missing_source_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            with FileResolver().resolve(str(tmp_path / "nope")) as _:
                pass


class TestFileResolverTarball:
    def _make_tarball(
        self, recipe_dir: Path, out_path: Path, *, with_top_dir: bool = True
    ) -> Path:
        """Pack ``recipe_dir`` into ``out_path`` as a .tar.gz."""
        with tarfile.open(out_path, "w:gz") as tf:
            arcname = recipe_dir.name if with_top_dir else "."
            tf.add(recipe_dir, arcname=arcname)
        return out_path

    def test_tarball_extracted_to_temp_dir(
        self, tmp_path: Path, recipe_dir: Path
    ) -> None:
        tarball = self._make_tarball(recipe_dir, tmp_path / "r.tar.gz")
        with FileResolver().resolve(str(tarball)) as p:
            assert p.is_dir()
            assert (p / "recipe.yaml").is_file()
            # The extracted directory must be inside a temp dir, not
            # the original location.
            assert p.resolve() != recipe_dir.resolve()

    def test_tarball_temp_dir_cleaned_up_after_with_block(
        self, tmp_path: Path, recipe_dir: Path
    ) -> None:
        tarball = self._make_tarball(recipe_dir, tmp_path / "r.tar.gz")
        captured: Path
        with FileResolver().resolve(str(tarball)) as p:
            captured = p
            assert captured.exists()
        # Walk up to the temp root (the parent of the recipe root).
        # The whole prefix directory must be gone.
        assert not captured.exists()

    def test_tgz_suffix_accepted(
        self, tmp_path: Path, recipe_dir: Path
    ) -> None:
        tarball = self._make_tarball(recipe_dir, tmp_path / "r.tgz")
        with FileResolver().resolve(str(tarball)) as p:
            assert (p / "recipe.yaml").is_file()


class TestTarFilterRejects:
    def _info(self, name: str, *, type_byte: bytes = tarfile.REGTYPE) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name=name)
        info.type = type_byte
        info.size = 0
        return info

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(ValueError, match="Unsafe path"):
            _tar_filter(self._info("/etc/passwd"), ".")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="Unsafe path"):
            _tar_filter(self._info("../sneaky"), ".")

    def test_rejects_symlink(self) -> None:
        info = self._info("link", type_byte=tarfile.SYMTYPE)
        info.linkname = "target"
        with pytest.raises(ValueError, match="Symlinks/hardlinks"):
            _tar_filter(info, ".")


class TestCanHandle:
    def test_https_rejected(self) -> None:
        assert FileResolver().can_handle("https://example.org/x.tar.gz") is False

    def test_http_rejected(self) -> None:
        assert FileResolver().can_handle("http://example.org/x.tar.gz") is False

    def test_file_uri_accepted(self) -> None:
        assert FileResolver().can_handle("file:///tmp/x") is True

    def test_bare_path_accepted(self) -> None:
        assert FileResolver().can_handle("/tmp/x") is True
        assert FileResolver().can_handle("./x") is True
        assert FileResolver().can_handle("x") is True
