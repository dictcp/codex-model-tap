from __future__ import annotations

from copy import deepcopy
from typing import Any


def patch_model_catalog(catalog: dict[str, Any], inject: tuple[dict[str, Any], ...], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    patched = deepcopy(catalog)
    models = patched.setdefault("models", [])
    if not isinstance(models, list):
        raise ValueError("model catalog has no list-valued 'models' field")

    by_slug = {
        model.get("slug"): model
        for model in models
        if isinstance(model, dict) and isinstance(model.get("slug"), str)
    }

    for slug, override in overrides.items():
        if slug in by_slug:
            by_slug[slug].update(deepcopy(override))

    for item in inject:
        if "slug" not in item:
            raise ValueError("injected model is missing required 'slug'")

        clone_from = item.get("clone_from")
        if clone_from and clone_from in by_slug:
            model = deepcopy(by_slug[clone_from])
        elif models and isinstance(models[0], dict):
            model = deepcopy(models[0])
        else:
            model = {}

        model.update({key: deepcopy(value) for key, value in item.items() if key != "clone_from"})
        slug = model["slug"]

        if slug in by_slug:
            by_slug[slug].update(model)
        else:
            models.append(model)
            by_slug[slug] = model

    return patched

