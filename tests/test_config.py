from codex_model_tap.config import load_config


def test_load_config_derives_injected_model_and_route(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
models:
  kimi-k2.6:
    clone_from: gpt-5.4-mini
    display_name: Kimi K2.6
    target_url: https://api.example.test/v1/responses
    target_model: kimi-k2.6
    bearer_token_env: KIMI_API_KEY
    headers:
      x-test: "1"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.inject_models == (
        {
            "slug": "kimi-k2.6",
            "clone_from": "gpt-5.4-mini",
            "display_name": "Kimi K2.6",
        },
    )
    assert config.override_models == {}
    assert config.response_routes[0].name == "kimi-k2.6"
    assert config.response_routes[0].target_url == "https://api.example.test/v1/responses"
    assert config.response_routes[0].match_models == ("kimi-k2.6",)
    assert config.response_routes[0].rewrite_model == "kimi-k2.6"
    assert config.response_routes[0].bearer_token_env == "KIMI_API_KEY"
    assert config.response_routes[0].headers == {"x-test": "1"}


def test_load_config_derives_existing_model_override_and_route(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
models:
  gpt-5.4-mini:
    display_name: GPT-5.4 Mini -> Kimi K2.6
    description: Routed locally.
    target_url: https://api.example.test/v1/responses
    target_model: kimi-k2.6
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.inject_models == ()
    assert config.override_models == {
        "gpt-5.4-mini": {
            "display_name": "GPT-5.4 Mini -> Kimi K2.6",
            "description": "Routed locally.",
        }
    }
    assert config.response_routes[0].match_models == ("gpt-5.4-mini",)
    assert config.response_routes[0].rewrite_model == "kimi-k2.6"
