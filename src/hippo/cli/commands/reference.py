"""Reference loader management commands."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def get_references_dir() -> Path:
    """Get the references directory path."""
    data_dir = Path.home() / ".hippo" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = data_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    return refs_dir


def discover_reference_loaders() -> list[dict[str, Any]]:
    """Discover reference loaders via entry points."""
    from importlib.metadata import entry_points

    loaders = []
    
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
        try:
            loader_class = ep.load()
            loaders.append(
                {
                    "name": ep.name,
                    "entry_point": ep.name,
                    "class": loader_class.__name__,
                    "module": loader_class.__module__,
                }
            )
        except Exception:
            pass

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
