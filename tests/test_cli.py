import sys

import pytest

from codex_model_tap import cli


def test_cli_wires_linux_pid_controls(monkeypatch):
    captured = {}

    def fake_execvpe(file, argv, env):
        captured["file"] = file
        captured["argv"] = argv
        captured["env"] = env
        raise RuntimeError("stop before exec")

    monkeypatch.setattr(cli.os, "execvpe", fake_execvpe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex-model-tap",
            "--config",
            "config.yaml",
            "--local",
            "codex",
            "--local-pid-file",
            "/tmp/codex.pid",
            "--local-control-socket",
            "/tmp/codex.sock",
        ],
    )

    with pytest.raises(RuntimeError, match="stop before exec"):
        cli.main()

    assert captured["argv"][:4] == [captured["file"], "--mode", "local:codex", "-s"]
    assert "--set" in captured["argv"]
    assert "codex_local_pid_file=/tmp/codex.pid" in captured["argv"]
    assert "codex_local_control_socket=/tmp/codex.sock" in captured["argv"]
