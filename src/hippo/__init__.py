"""Deprecated alias: the ``hippo`` package is now ``mosaic`` (ADR-0004).

This shim keeps ``import hippo`` and ``import hippo.<submodule>`` working
during the deprecation window. Submodule imports resolve to the *same*
module objects as their ``mosaic`` counterparts (a meta-path finder aliases
``hippo.*`` onto ``mosaic.*``), so ``isinstance``/``issubclass`` checks and
module identity hold across both spellings.

Note: the finder is inserted at the *front* of ``sys.meta_path``. Once
``hippo.core`` is aliased to the ``mosaic.core`` package object, the
standard ``PathFinder`` would otherwise resolve ``hippo.core.client``
through the parent's ``__path__`` and re-execute the module under the
legacy name — breaking module identity. Intercepting ``hippo.*`` first
guarantees every spelling maps to the one canonical module object.
"""

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

warnings.warn(
    "'hippo' has been renamed to 'mosaic' (ADR-0004); the 'hippo' alias will "
    "be removed in a future release. Use 'import mosaic'.",
    DeprecationWarning,
    stacklevel=2,
)

_mosaic = importlib.import_module("mosaic")

#: Module attributes the import machinery stamps with the aliased (hippo.*)
#: spelling on the shared module object; restored in ``exec_module`` so the
#: canonical mosaic identity stays intact.
_PRESERVED_ATTRS = ("__name__", "__qualname__", "__spec__", "__loader__", "__package__")


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target):
        self._target = target
        self._original = {}

    def create_module(self, spec):
        mod = importlib.import_module(self._target)
        self._original = {
            key: getattr(mod, key) for key in _PRESERVED_ATTRS if hasattr(mod, key)
        }
        sys.modules[spec.name] = mod
        return mod

    def exec_module(self, module):
        # Undo the attribute stamping done by ``module_from_spec`` — the
        # module object is shared with the canonical mosaic spelling.
        for key, value in self._original.items():
            try:
                setattr(module, key, value)
            except AttributeError:  # pragma: no cover — read-only attr
                pass


class _AliasFinder(importlib.abc.MetaPathFinder):
    _mosaic_alias_finder = True  # idempotence marker (see install below)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("hippo."):
            return importlib.util.spec_from_loader(
                fullname, _AliasLoader("mosaic" + fullname[5:])
            )
        return None


# Install once, at the FRONT of sys.meta_path (see module docstring).
if not any(
    getattr(finder, "_mosaic_alias_finder", False) for finder in sys.meta_path
):
    sys.meta_path.insert(0, _AliasFinder())


def __getattr__(name):  # hippo.HippoClient, hippo.__version__, ...
    return getattr(_mosaic, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_mosaic)))
