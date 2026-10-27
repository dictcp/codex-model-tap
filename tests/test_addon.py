import json
from types import SimpleNamespace

from mitmproxy import ctx
from mitmproxy import http

from codex_model_tap.addon import CodexModelTap
from codex_model_tap.config import AppConfig, ResponseRoute


def test_apply_upstream_body_compat_forces_plain_json_bytes():
    flow = http.HTTPFlow(None, None)
    flow.request = http.Request.make(
        "POST",
        "https://chatgpt.com/backend-api/codex/responses",
        content=b"old",
        headers={
            "content-type": "application/json",
            "content-encoding": "zstd",
            "transfer-encoding": "chunked",
            "content-length": "999",
        },
    )

    body = b'{"model":"kimi-k2.6"}'
    CodexModelTap()._apply_upstream_body_compat(flow, body)

    assert flow.request.raw_content == body
    assert flow.request.headers["content-type"] == "application/json"
    assert flow.request.headers["content-length"] == str(len(body))
    assert "content-encoding" not in flow.request.headers
    assert "transfer-encoding" not in flow.request.headers


def test_request_reroute_never_forwards_zstd_body(monkeypatch):
    monkeypatch.setattr(ctx, "log", SimpleNamespace(info=lambda *_args, **_kwargs: None), raising=False)
    body = json.dumps({"model": "gpt-5.4-mini", "input": "hi"}).encode()
    flow = http.HTTPFlow(None, None)
    flow.request = http.Request.make(
        "POST",
        "https://chatgpt.com/backend-api/codex/responses",
        content=body,
        headers={
            "content-type": "application/json",
        },
    )
    flow.request.encode("zstd")
    assert flow.request.raw_content.startswith(b"\x28\xb5\x2f\xfd")

    addon = CodexModelTap()
    addon.config = AppConfig(
        response_routes=(
            ResponseRoute(
                name="gpt-5.4-mini",
                target_url="http://ai/v1/responses",
                match_models=("gpt-5.4-mini",),
                rewrite_model="kimi-k2.6",
                headers={"x-codex-model-tap": "1"},
            ),
        )
    )

    addon.request(flow)

    assert flow.request.host == "ai"
    assert flow.request.path == "/v1/responses"
    assert flow.request.raw_content is not None
    assert flow.request.raw_content.startswith(b"{")
    assert not flow.request.raw_content.startswith(b"\x28\xb5\x2f\xfd")
    assert json.loads(flow.request.raw_content)["model"] == "kimi-k2.6"
    assert "content-encoding" not in flow.request.headers
    assert flow.request.headers["content-length"] == str(len(flow.request.raw_content))
