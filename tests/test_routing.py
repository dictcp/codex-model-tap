import json

from codex_model_tap.config import ResponseRoute
from codex_model_tap.routing import is_websocket_upgrade, route_responses_request


def test_route_responses_request_rewrites_matching_model():
    route = ResponseRoute(
        name="kimi",
        target_url="https://api.example.test/v1/responses",
        match_models=("gpt-5.4-mini", "kimi-k2.6"),
        rewrite_model="kimi-k2.6",
    )

    routed = route_responses_request(json.dumps({"model": "gpt-5.4-mini", "input": "hi"}).encode(), (route,))

    assert routed is not None
    assert routed.route.target_url == "https://api.example.test/v1/responses"
    assert routed.model_before == "gpt-5.4-mini"
    assert routed.model_after == "kimi-k2.6"
    assert json.loads(routed.body)["model"] == "kimi-k2.6"


def test_route_responses_request_ignores_non_matching_model():
    route = ResponseRoute(
        name="kimi",
        target_url="https://api.example.test/v1/responses",
        match_models=("kimi-k2.6",),
    )

    assert route_responses_request(json.dumps({"model": "gpt-5.5"}).encode(), (route,)) is None


def test_route_responses_request_ignores_non_json_body():
    route = ResponseRoute(
        name="kimi",
        target_url="https://api.example.test/v1/responses",
        match_models=("kimi-k2.6",),
    )

    assert route_responses_request(b"\xb5\x00not-json", (route,)) is None


def test_is_websocket_upgrade_requires_upgrade_and_websocket_headers():
    assert is_websocket_upgrade({"connection": "keep-alive, Upgrade", "upgrade": "websocket"})
    assert not is_websocket_upgrade({"connection": "keep-alive", "upgrade": "websocket"})
    assert not is_websocket_upgrade({"connection": "Upgrade", "upgrade": "h2c"})
