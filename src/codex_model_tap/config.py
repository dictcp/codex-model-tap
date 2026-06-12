from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8080


@dataclass(frozen=True)
class ModelConfig:
    slug: str
    target_url: str | None = None
    target_model: str | None = None
    bearer_token_env: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)

    @property
    def routed(self) -> bool:
        return self.target_url is not None


@dataclass(frozen=True)
class ResponseRoute:
    name: str
    target_url: str
    match_models: tuple[str, ...] = ()
    rewrite_model: str | None = None
    bearer_token_env: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    strip_chatgpt_headers: bool = True


@dataclass(frozen=True)
class AppConfig:
    models: tuple[ModelConfig, ...] = ()
    inject_models: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    override_models: dict[str, dict[str, Any]] = field(default_factory=dict)
    response_routes: tuple[ResponseRoute, ...] = field(default_factory=tuple)


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    models = tuple(_parse_models(raw.get("models") or {}))
    return AppConfig(
        models=models,
        inject_models=_catalog_injections(models),
        override_models=_catalog_overrides(models),
        response_routes=_response_routes(models),
    )


def _parse_models(raw_models: Any) -> list[ModelConfig]:
    if isinstance(raw_models, dict):
        items = [{"slug": slug, **(value or {})} for slug, value in raw_models.items()]
    elif isinstance(raw_models, list):
        items = raw_models
    else:
        raise ValueError("'models' must be a mapping or list")

    return [_parse_model(item) for item in items]


def _parse_model(raw_model: Any) -> ModelConfig:
    if not isinstance(raw_model, dict):
        raise ValueError("each model must be an object")

    model = dict(raw_model)
    slug = model.pop("slug", None)
    if not isinstance(slug, str) or not slug:
        raise ValueError("each model must define a non-empty slug")

    target_url = model.pop("target_url", None)
    target_model = model.pop("target_model", None)
    bearer_token_env = model.pop("bearer_token_env", None)
    headers = model.pop("headers", {}) or {}
    catalog = model.pop("catalog", {}) or {}

    if not isinstance(headers, dict):
        raise ValueError(f"model {slug!r} has non-object headers")
    if not isinstance(catalog, dict):
        raise ValueError(f"model {slug!r} has non-object catalog")

    catalog = {**model, **catalog}
    catalog["slug"] = slug

    return ModelConfig(
        slug=slug,
        target_url=target_url,
        target_model=target_model,
        bearer_token_env=bearer_token_env,
        headers={str(key): str(value) for key, value in headers.items()},
        catalog=catalog,
    )


def _catalog_injections(models: tuple[ModelConfig, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(model.catalog for model in models if "clone_from" in model.catalog)


def _catalog_overrides(models: tuple[ModelConfig, ...]) -> dict[str, dict[str, Any]]:
    return {
        model.slug: {key: value for key, value in model.catalog.items() if key != "slug"}
        for model in models
        if "clone_from" not in model.catalog
    }


def _response_routes(models: tuple[ModelConfig, ...]) -> tuple[ResponseRoute, ...]:
    return tuple(
        ResponseRoute(
            name=model.slug,
            target_url=model.target_url or "",
            match_models=(model.slug,),
            rewrite_model=model.target_model,
            bearer_token_env=model.bearer_token_env,
            headers=model.headers,
            strip_chatgpt_headers=True,
        )
        for model in models
        if model.routed
    )
