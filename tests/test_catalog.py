from codex_model_tap.catalog import patch_model_catalog


def test_patch_model_catalog_injects_by_cloning_existing_model():
    catalog = {
        "models": [
            {
                "slug": "gpt-5.4-mini",
                "display_name": "GPT-5.4 Mini",
                "context_window": 128000,
                "supported_in_api": True,
            }
        ]
    }

    patched = patch_model_catalog(
        catalog,
        (
            {
                "slug": "kimi-k2.6",
                "clone_from": "gpt-5.4-mini",
                "display_name": "Kimi K2.6",
            },
        ),
        {},
    )

    assert patched["models"][1]["slug"] == "kimi-k2.6"
    assert patched["models"][1]["display_name"] == "Kimi K2.6"
    assert patched["models"][1]["context_window"] == 128000


def test_patch_model_catalog_overrides_existing_model():
    catalog = {"models": [{"slug": "gpt-5.4-mini", "display_name": "GPT-5.4 Mini"}]}

    patched = patch_model_catalog(
        catalog,
        (),
        {"gpt-5.4-mini": {"display_name": "GPT-5.4 Mini -> Kimi K2.6"}},
    )

    assert patched["models"][0]["display_name"] == "GPT-5.4 Mini -> Kimi K2.6"
