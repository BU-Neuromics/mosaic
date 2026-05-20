"""Reference loader management commands."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from hippo.core.loaders.reference import ReferenceLoader


class ReferenceLoaderRegistrationError(TypeError):
    """Raised when a ``hippo.reference_loaders`` entry point does not
    resolve to a concrete :class:`ReferenceLoader` subclass."""


def reference_cache_root() -> Path:
    """Resolve the directory holding per-loader reference caches.

    Mirrors :meth:`HippoClient._reference_cache_root` so the CLI can
    operate without instantiating a full client (sec2 §2.14.3,
    decision D2.14.E). ``$HIPPO_CACHE_DIR`` wins when set; otherwise
    ``~/.cache/hippo/references/``.
    """
    env = os.environ.get("HIPPO_CACHE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "hippo" / "references"


def clean_reference_cache(name: str | None = None) -> dict[str, Any]:
    """Remove cached reference-loader data.

    With ``name``, removes only that loader's cache subtree; other
    loaders are untouched. Without ``name``, removes the entire cache
    root. Missing targets are a silent no-op (idempotent) so the verb
    is safe to run on a fresh machine.
    """
    root = reference_cache_root()
    if name is not None:
        target = root / name
        existed = target.exists()
        if existed:
            shutil.rmtree(target)
        return {"removed": existed, "path": str(target), "scope": name}
    existed = root.exists()
    if existed:
        shutil.rmtree(root)
    return {"removed": existed, "path": str(root), "scope": None}


def get_references_dir() -> Path:
    """Get the references directory path."""
    data_dir = Path.home() / ".hippo" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = data_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    return refs_dir


def discover_reference_loaders() -> list[dict[str, Any]]:
    """Discover and instantiate reference loaders via entry points.

    Each entry point in the ``hippo.reference_loaders`` group must point
    at a concrete :class:`ReferenceLoader` subclass. The class is
    instantiated eagerly so that callers receive a ready-to-use loader
    surface; an entry point pointing at anything else raises
    :class:`ReferenceLoaderRegistrationError` with a message identifying
    the offending entry point.
    """
    from importlib.metadata import entry_points

    loaders: list[dict[str, Any]] = []

    # Handle both new and old API versions
    try:
        eps = entry_points()
        ref_eps = eps.select(group="hippo.reference_loaders")
        eps_list = list(ref_eps)
    except (TypeError, AttributeError):
        # Fall back to the older method if available
        try:
            eps = entry_points()
            eps_list = list(eps["hippo.reference_loaders"])
        except (KeyError, TypeError):
            eps_list = []

    for ep in eps_list:
        loaded = ep.load()
        if not (isinstance(loaded, type) and issubclass(loaded, ReferenceLoader)):
            raise ReferenceLoaderRegistrationError(
                f"Entry point 'hippo.reference_loaders:{ep.name}' "
                f"({ep.value}) is not a subclass of "
                f"hippo.core.loaders.reference.ReferenceLoader"
            )
        instance = loaded()
        loaders.append(
            {
                "name": ep.name,
                "entry_point": ep.name,
                "class": loaded.__name__,
                "module": loaded.__module__,
                "description": getattr(instance, "description", ""),
                "instance": instance,
            }
        )

    return loaders


def list_reference_loaders() -> list[dict[str, Any]]:
    """List all installed reference loader packages."""
    discovered = discover_reference_loaders()

    refs_dir = get_references_dir()
    installed_file = refs_dir / "installed.json"

    installed = []
    if installed_file.exists():
        try:
            installed = json.loads(installed_file.read_text())
        except Exception:
            installed = []

    result = []
    installed_names = set()

    for pkg in installed:
        loader = {
            "name": pkg.get("name", "unknown"),
            "version": pkg.get("version", "unknown"),
            "description": pkg.get("description", ""),
            "source": pkg.get("source", "PyPI"),
            "installed": True,
        }
        result.append(loader)
        installed_names.add(pkg.get("name"))

    for loader in discovered:
        if loader["name"] not in installed_names:
            loader["installed"] = False
            result.append(loader)

    return result


def install_reference_loader(package: str, source: str | None = None) -> dict[str, Any]:
    """Install a reference loader package."""
    from importlib.metadata import version

    refs_dir = get_references_dir()
    installed_file = refs_dir / "installed.json"

    installed = []
    if installed_file.exists():
        try:
            installed = json.loads(installed_file.read_text())
        except Exception:
            installed = []

    for pkg in installed:
        if pkg.get("name") == package:
            raise ValueError(f"Package '{package}' is already installed")

    # Check if we have a source specified (local path or custom URL)
    if source and (source.startswith("/") or source.startswith(".")):
        # Local file installation
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--force-reinstall", source
            ])
            pkg_version = version(package)
        except Exception as e:
            raise ValueError(
                f"Failed to install package from local source '{source}'. Error: {str(e)}"
            )
    else:
        # Try to find and install via pip
        try:
            pkg_version = version(package)
        except Exception:
            # If not found locally, attempt to install from pip
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", package
                ])
                pkg_version = version(package)
            except subprocess.CalledProcessError:
                raise ValueError(
                    f"Failed to install package '{package}'. Please verify the package name and try again."
                )
            except Exception:
                raise ValueError(
                    f"Package '{package}' not found. Please verify the package name and try again."
                )

    installed.append(
        {
            "name": package,
            "version": pkg_version,
            "source": source or "PyPI",
        }
    )

    installed_file.write_text(json.dumps(installed, indent=2))

    return {
        "name": package,
        "version": pkg_version,
    }


def list_reference_loaders() -> list[dict[str, Any]]:
    """List all installed reference loader packages."""
    discovered = discover_reference_loaders()

    refs_dir = get_references_dir()
    installed_file = refs_dir / "installed.json"

    installed = []
    if installed_file.exists():
        try:
            installed = json.loads(installed_file.read_text())
        except Exception:
            installed = []

    result = []
    installed_names = set()

    for pkg in installed:
        loader = {
            "name": pkg.get("name", "unknown"),
            "version": pkg.get("version", "unknown"),
            "description": pkg.get("description", ""),
            "source": pkg.get("source", "PyPI"),
            "installed": True,
        }
        result.append(loader)
        installed_names.add(pkg.get("name"))

    for loader in discovered:
        if loader["name"] not in installed_names:
            loader["installed"] = False
            result.append(loader)

    return result


def install_reference_loader(package: str, source: str | None = None) -> dict[str, Any]:
    """Install a reference loader package."""
    from importlib.metadata import version

    refs_dir = get_references_dir()
    installed_file = refs_dir / "installed.json"

    installed = []
    if installed_file.exists():
        try:
            installed = json.loads(installed_file.read_text())
        except Exception:
            installed = []

    for pkg in installed:
        if pkg.get("name") == package:
            raise ValueError(f"Package '{package}' is already installed")

    # Check if we have a source specified (local path or custom URL)
    if source and (source.startswith("/") or source.startswith(".")):
        # Local file installation
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--force-reinstall", source]
            )
            pkg_version = version(package)
        except Exception as e:
            raise ValueError(
                f"Failed to install package from local source '{source}'. Error: {str(e)}"
            )
    else:
        # Try to find and install via pip
        try:
            pkg_version = version(package)
        except Exception:
            # If not found locally, attempt to install from pip
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                pkg_version = version(package)
            except subprocess.CalledProcessError:
                raise ValueError(
                    f"Failed to install package '{package}'. Please verify the package name and try again."
                )
            except Exception:
                raise ValueError(
                    f"Package '{package}' not found. Please verify the package name and try again."
                )

    installed.append(
        {
            "name": package,
            "version": pkg_version,
            "source": source or "PyPI",
        }
    )

    installed_file.write_text(json.dumps(installed, indent=2))

    return {
        "name": package,
        "version": pkg_version,
    }
