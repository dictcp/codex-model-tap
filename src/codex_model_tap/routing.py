from __future__ import annotations

import json
from json import JSONDecodeError
from dataclasses import dataclass
from typing import Any

from .config import ResponseRoute


@dataclass(frozen=True)
class RoutedRequest:
    route: ResponseRoute
    body: bytes
    model_before: str | None
    model_after: str | None


def route_responses_request(body: bytes, routes: tuple[ResponseRoute, ...]) -> RoutedRequest | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    model = payload.get("model")
    if not isinstance(model, str):
        return None

    for route in routes:
        if route.match_models and model not in route.match_models:
            continue

        model_after = model
        if route.rewrite_model:
            payload["model"] = route.rewrite_model
            model_after = route.rewrite_model

        return RoutedRequest(
            route=route,
            body=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            model_before=model,
            model_after=model_after,
        )

    return None


def is_websocket_upgrade(headers: Any) -> bool:
    upgrade = headers.get("upgrade", "")
    connection = headers.get("connection", "")
    return "websocket" in upgrade.lower() and "upgrade" in connection.lower()
