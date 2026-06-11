# codex-model-tap

Local mitmproxy addon for selectively intercepting Codex traffic to `chatgpt.com`.

It does two things and leaves other traffic alone:

- Injects or overrides entries in `GET /backend-api/codex/models?...`.
- Reroutes selected `POST /backend-api/codex/responses` requests to a configured upstream endpoint, with optional model rewrite such as `gpt-5.4-mini` -> `kimi-k2.6`.
- Blocks WebSocket upgrade attempts to `/backend-api/codex/responses` so Codex can fall back to REST.

## Setup

```bash
cd /home/dick/workspaces/codex-model-tap
mise install
mise exec -- python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp config.example.yaml config.yaml
```

Set the upstream token if your config uses `bearer_token_env`:

```bash
export MOONSHOT_API_KEY=...
```

## Run

Local Capture requires elevated privileges on most systems. This project targets mitmproxy 12 because it supports app-level Local Capture on Linux. The common form is:

```bash
sudo .venv/bin/mitmdump \
  --mode local:codex \
  -s src/codex_model_tap/addon.py \
  --set codex_mitm_config=/home/dick/workspaces/codex-model-tap/config.yaml
```

Or use the helper, which execs mitmdump with the same addon:

```bash
sudo .venv/bin/codex-model-tap --config /home/dick/workspaces/codex-model-tap/config.yaml --local codex
```

Normal HTTP proxy mode:

```bash
.venv/bin/mitmdump \
  --mode regular \
  --listen-host 127.0.0.1 \
  --listen-port 8080 \
  -s src/codex_model_tap/addon.py \
  --set codex_mitm_config=/home/dick/workspaces/codex-model-tap/config.yaml
```

Point a process at regular proxy mode with:

```bash
HTTPS_PROXY=http://127.0.0.1:8080 HTTP_PROXY=http://127.0.0.1:8080 codex
```

Install/trust the mitmproxy CA for the user or system that runs Codex. You said root/CA override is acceptable, so this repo assumes certificate setup is handled outside the addon.

## Config Shape

`config.example.yaml` is intentionally model-focused. Each key under `models` is a local Codex model slug:

- If the slug does not exist in ChatGPT's catalog, set `clone_from` to copy a real catalog model and then apply your local catalog fields.
- If the slug already exists, catalog fields such as `display_name` and `description` override the original entry.
- `target_url` makes requests for that local slug route to another responses endpoint.
- `target_model` rewrites the JSON request body's `model` before forwarding.
- `bearer_token_env` names the environment variable used for the upstream Authorization bearer token.
- `headers` adds extra upstream request headers for that model.

ChatGPT host/path matching, WebSocket upgrade blocking, stripped ChatGPT headers, and local listen defaults are code-level behavior now. The config stays about models and where each model routes.

The upstream endpoint must accept the Codex responses payload shape you forward. If the upstream is OpenAI-compatible but not byte-for-byte compatible, add a transformer before forwarding.

## Tests

```bash
pytest
```
