from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from mitmproxy import ctx, http

from codex_model_tap.catalog import patch_model_catalog
from codex_model_tap.config import (
    AppConfig,
    load_config,
)
from codex_model_tap.routing import RoutedRequest, is_websocket_upgrade, route_responses_request
from codex_model_tap.linux_pid_control import addons as linux_pid_control_addons


class CodexModelTap:
    def __init__(self) -> None:
        self.config: AppConfig | None = None

    def load(self, loader) -> None:
        loader.add_option(
            name="codex_mitm_config",
            typespec=str,
            default="config.yaml",
            help="Path to codex-model-tap YAML config.",
        )

    def configure(self, updates) -> None:
        if "codex_mitm_config" in updates:
            self.config = load_config(ctx.options.codex_mitm_config)
            ctx.log.info(f"codex-model-tap loaded {ctx.options.codex_mitm_config}")

    def request(self, flow: http.HTTPFlow) -> None:
        config = self.config
        if not config or not self._is_chatgpt_path(flow, "/backend-api/codex/responses"):
            return

        if is_websocket_upgrade(flow.request.headers):
            self._block_websocket_upgrade(flow)
            ctx.log.info("codex-model-tap blocked websocket upgrade for /backend-api/codex/responses")
            return

        routed = route_responses_request(flow.request.content or b"{}", config.response_routes)

        if not routed:
            return

        self._apply_route(flow, routed)
        ctx.log.info(
            "codex-model-tap routed /backend-api/codex/responses "
            f"model={routed.model_before} -> {routed.model_after} upstream={routed.route.target_url}"
        )

    def response(self, flow: http.HTTPFlow) -> None:
        config = self.config
        if not config or not self._is_chatgpt_path(flow, "/backend-api/codex/models"):
            return

        content_type = flow.response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            return

        try:
            catalog = json.loads(flow.response.get_text())
            patched = patch_model_catalog(catalog, config.inject_models, config.override_models)
            flow.response.set_text(json.dumps(patched, separators=(",", ":"), ensure_ascii=False))
            flow.response.headers.pop("etag", None)
            flow.response.headers.pop("content-length", None)
            ctx.log.info("codex-model-tap patched model catalog")
        except Exception as exc:
            ctx.log.warn(f"codex-model-tap could not patch model catalog: {exc}")

    def _is_chatgpt_path(self, flow: http.HTTPFlow, path: str) -> bool:
        host = flow.request.pretty_host or flow.request.host
        return host == "chatgpt.com" and flow.request.path.split("?", 1)[0] == path

    def _apply_route(self, flow: http.HTTPFlow, routed: RoutedRequest) -> None:
        route = routed.route
        parsed = urlsplit(route.target_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid target_url for route {route.name}: {route.target_url}")

        flow.request.scheme = parsed.scheme
        flow.request.host = parsed.hostname or parsed.netloc
        flow.request.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        flow.request.path = parsed.path or "/"
        if parsed.query:
            flow.request.path = f"{flow.request.path}?{parsed.query}"

        flow.request.headers["host"] = parsed.netloc
        self._apply_upstream_body_compat(flow, routed.body)

        if route.strip_chatgpt_headers:
            for header in (
                "authorization",
                "cookie",
                "chatgpt-account-id",
                "x-oai-attestation",
                "x-openai-fedramp",
                "x-openai-internal-codex-responses-lite",
            ):
                flow.request.headers.pop(header, None)

        if route.bearer_token_env:
            token = os.environ.get(route.bearer_token_env)
            if not token:
                raise RuntimeError(f"missing required env var {route.bearer_token_env} for route {route.name}")
            flow.request.headers["authorization"] = f"Bearer {token}"

        for key, value in route.headers.items():
            flow.request.headers[key] = value

    def _apply_upstream_body_compat(self, flow: http.HTTPFlow, body: bytes) -> None:
        # FIXME: http://ai/v1/responses currently parses zstd bytes as JSON.
        # Keep rerouted requests as plain JSON until that upstream supports
        # Content-Encoding: zstd request bodies.
        flow.request.headers["content-type"] = "application/json"
        flow.request.headers.pop("content-encoding", None)
        flow.request.headers.pop("transfer-encoding", None)
        flow.request.raw_content = body
        flow.request.headers["content-length"] = str(len(body))

    def _block_websocket_upgrade(self, flow: http.HTTPFlow) -> None:
        flow.response = http.Response.make(
            426,
            "WebSocket upgrade is not available at this moment.\n".encode("utf-8"),
            {
                "content-type": "text/plain; charset=utf-8",
                "x-codex-model-tap-websocket-blocked": "1",
            },
        )
        flow.response.reason = "OK"


addons = [CodexModelTap(), *linux_pid_control_addons]
