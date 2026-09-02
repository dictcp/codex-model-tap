from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import sysconfig

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

    if sys.platform == "linux" and (
        mode == "local" or mode.startswith("local:")
    ):
        # mitmproxy's Linux redirector invokes sudo with --preserve-env and
        # promotes every line on stderr to an error. Keep a project-scoped
        # shim ahead of PATH for hosts whose sudo implementation warns that
        # this option is unsupported.
        sudo_shim = Path(__file__).with_name("compat") / "sudo"
        if sudo_shim.is_file():
            os.environ["PATH"] = os.pathsep.join(
                [str(sudo_shim.parent), os.environ.get("PATH", "")]
            )

    # Resolve mitmdump next to this entry point. This avoids accidentally
    # running a different migrated/global virtual environment.
    mitmdump = Path(sysconfig.get_path("scripts")) / "mitmdump"
    mitmdump_command = str(mitmdump) if mitmdump.is_file() else "mitmdump"

    argv = [
        mitmdump_command,
        "--mode",
        mode,
        "-s",
        os.path.join(os.path.dirname(__file__), "addon.py"),
        "--set",
        f"codex_mitm_config={args.config}",
    ]

    argv.extend(["--listen-host", args.listen_host or LISTEN_HOST])
    argv.extend(["--listen-port", args.listen_port or str(LISTEN_PORT)])

    os.execvpe(argv[0], argv, os.environ)
    raise SystemExit(127)


if __name__ == "__main__":
    main()
