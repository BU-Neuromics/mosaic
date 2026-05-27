"""Recipe subsystem dataclasses (sec10 §10.3).

Python types describing recipe manifests, install plans, install
results, and inspection / diff reports. No behavior — :class:`RecipeService`
(``hippo.core.recipe_service``) owns the verbs.

Re-exported here so callers import from one place:

    from hippo.core.recipe import RecipeManifest, RecipeRef, InstalledRecipe
"""

from __future__ import annotations

from hippo.core.recipe.dataclasses import (
    ImportPlan,
    ImportResult,
    InstalledRecipe,
    RecipeAuthor,
    RecipeDiff,
    RecipeExport,
    RecipeManifest,
    RecipeRef,
    RecipeReport,
    RecipeRequires,
)
from hippo.core.recipe.digest import canonical_content_hash
from hippo.core.recipe.resolver import (
    FileResolver,
    HttpsResolver,
    RecipeResolver,
    default_recipe_cache_dir,
)

__all__ = [
    "FileResolver",
    "HttpsResolver",
    "ImportPlan",
    "ImportResult",
    "InstalledRecipe",
    "RecipeAuthor",
    "RecipeDiff",
    "RecipeExport",
    "RecipeManifest",
    "RecipeRef",
    "RecipeReport",
    "RecipeRequires",
    "RecipeResolver",
    "canonical_content_hash",
    "default_recipe_cache_dir",
]
