"""Recipe resolvers — map a ``source`` (URI or path) to a recipe directory.

A :class:`RecipeResolver` exposes ``resolve(source, *, base_dir=None)``
which returns a context manager yielding a :class:`pathlib.Path` to a
recipe *directory* — the form ``RecipeService`` operates on (parse
``recipe.yaml``, hash the contents, etc.). Tarball sources are
extracted into a temp directory whose lifetime is bounded by the
context manager.

Phase 3 (PTS-291) introduces two implementations:

- :class:`FileResolver` (PR 5) — handles ``file:`` URIs, bare absolute
  paths, and bare relative paths. Relative paths resolve against the
  ``base_dir`` passed to ``resolve(...)`` (the importing recipe's
  directory when called transitively, or the CWD for a top-level
  invocation).
- :class:`HttpsResolver` (PR 6) — fetches over HTTPS into a
  content-addressable cache.
"""

from __future__ import annotations

import tarfile
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Iterator, Optional
from urllib.parse import unquote, urlparse


class RecipeResolver(ABC):
    """Locate a recipe by source URI/path and yield a directory to operate on.

    Implementations are stateless beyond construction-time config.
    ``can_handle(source)`` is used by ``RecipeService`` to dispatch to
    the right resolver from its registered list.
    """

    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """Return True if this resolver knows how to materialize ``source``."""

    @abstractmethod
    def resolve(
        self,
        source: str,
        *,
        base_dir: Optional[Path] = None,
    ) -> ContextManager[Path]:
        """Return a context manager yielding the recipe root directory.

        Tarball sources are extracted into a temp directory whose
        lifetime equals the with-block; the temp dir is removed on
        exit. Directory sources are yielded as-is and never cleaned up
        by the resolver.

        ``base_dir`` resolves bare relative paths and ``file:`` URIs
        whose path component is relative. When ``None``, callers should
        pass ``Path.cwd()`` explicitly for top-level invocations.
        """


class FileResolver(RecipeResolver):
    """Resolver for ``file:`` URIs and bare filesystem paths (sec10 §10.4.1).

    Accepted source forms:

    - ``file:///abs/path`` — RFC 8089 absolute file URI.
    - ``file:./rel/path`` or ``file:rel/path`` — file URI with a
      relative path component (Hippo-specific convenience documented
      in sec10 §10.3.3).
    - ``/abs/path`` — bare absolute path.
    - ``rel/path`` or ``./rel/path`` — bare relative path, resolved
      against ``base_dir``.

    Both directory recipes and ``.tar.gz`` / ``.tgz`` / ``.tar`` tarballs
    are accepted; tarballs are extracted into a temp dir whose root
    must be the recipe directory (sec10 §10.4 layout).
    """

    _TARBALL_SUFFIXES = (".tar.gz", ".tgz", ".tar")

    def can_handle(self, source: str) -> bool:
        if source.startswith("https:") or source.startswith("http:"):
            return False
        if source.startswith("file:"):
            return True
        return True

    @contextmanager
    def resolve(
        self,
        source: str,
        *,
        base_dir: Optional[Path] = None,
    ) -> Iterator[Path]:
        path = self._resolve_path(source, base_dir=base_dir)
        if not path.exists():
            raise FileNotFoundError(
                f"Recipe source not found: {source} (resolved to {path})"
            )

        if path.is_dir():
            yield path
            return

        if path.is_file() and self._is_tarball(path):
            with tempfile.TemporaryDirectory(prefix="hippo-recipe-") as tmp:
                tmp_path = Path(tmp)
                recipe_dir = self._extract_tarball(path, tmp_path)
                yield recipe_dir
            return

        raise ValueError(
            f"Recipe source must be a directory or tarball: {source} "
            f"(resolved to {path})"
        )

    def _resolve_path(self, source: str, *, base_dir: Optional[Path]) -> Path:
        if source.startswith("file:"):
            parsed = urlparse(source)
            raw = unquote(parsed.path or "")
            if parsed.netloc and parsed.netloc not in ("", "localhost"):
                raise ValueError(
                    f"file: URIs with a non-empty/non-localhost netloc are not "
                    f"supported: {source}"
                )
            candidate = Path(raw)
        else:
            candidate = Path(source)

        if candidate.is_absolute():
            return candidate
        if base_dir is None:
            base_dir = Path.cwd()
        return (base_dir / candidate).resolve()

    def _is_tarball(self, path: Path) -> bool:
        name = path.name.lower()
        return any(name.endswith(suf) for suf in self._TARBALL_SUFFIXES)

    def _extract_tarball(self, tarball: Path, dest: Path) -> Path:
        """Extract ``tarball`` under ``dest`` and return the recipe root.

        The tarball MUST contain the recipe root as a single top-level
        directory (sec10 §10.4 layout). When the archive contains a
        single top-level directory, that directory is returned as the
        recipe root. When the archive contains multiple top-level
        entries, ``dest`` itself is treated as the recipe root.
        """
        with tarfile.open(tarball, "r:*") as tf:
            tf.extractall(dest, filter=_tar_filter)

        entries = list(dest.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return dest


def _tar_filter(member: tarfile.TarInfo, dest: str) -> tarfile.TarInfo:
    """Strict tarfile extraction filter rejecting traversal + exotic entries.

    Symlinks, hardlinks, devices, and absolute or parent-traversing
    paths are rejected outright — v1 recipes are flat content trees.
    """
    name = member.name
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError(f"Unsafe path in recipe tarball: {name!r}")
    if member.isdev() or member.isfifo() or member.ischr() or member.isblk():
        raise ValueError(f"Unsupported entry in recipe tarball: {name!r}")
    if member.issym() or member.islnk():
        raise ValueError(
            f"Symlinks/hardlinks are not allowed in recipe tarballs: {name!r}"
        )
    return member


__all__ = ["RecipeResolver", "FileResolver"]
