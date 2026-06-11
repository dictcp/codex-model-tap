from __future__ import annotations

import argparse
import os

from codex_model_tap.config import LISTEN_HOST, LISTEN_PORT


def main() -> None:
    parser = argparse.ArgumentParser(description="Run codex-model-tap with mitmdump.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config.")
    parser.add_argument("--listen-host", default=None, help="mitmproxy listen host override.")
    parser.add_argument("--listen-port", default=None, help="mitmproxy listen port override.")
    parser.add_argument("--mode", default=None, help="Full mitmproxy mode value. Defaults to local:<--local>.")
    parser.add_argument("--local", default="codex", help="mitmproxy local capture selector used when --mode is omitted.")
    args = parser.parse_args()
    mode = args.mode or f"local:{args.local}"

    argv = [
        "mitmdump",
        "--mode",
        mode,
        "-s",
        os.path.join(os.path.dirname(__file__), "addon.py"),
        "--set",
        f"codex_mitm_config={args.config}",
    ]

    argv.extend(["--listen-host", args.listen_host or LISTEN_HOST])
    argv.extend(["--listen-port", args.listen_port or str(LISTEN_PORT)])

    os.execvp(argv[0], argv)
    raise SystemExit(127)


if __name__ == "__main__":
    main()
