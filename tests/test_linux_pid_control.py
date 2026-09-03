import asyncio

import pytest
from mitmproxy import ctx

import codex_model_tap.linux_pid_control as linux_pid_control
from codex_model_tap.linux_pid_control import LinuxLocalPidControl, parse_pid, replace_local_pid


class FakeOptions:
    mode = ["local:codex"]
    codex_local_pid = None
    codex_local_pid_file = None
    codex_local_control_socket = None
    codex_local_pid_poll_interval = 0.01

    def __init__(self):
        self.updates = []

    def update(self, **values):
        self.updates.append(values)
        for name, value in values.items():
            setattr(self, name, value)


def install_fake_options(monkeypatch):
    options = FakeOptions()
    monkeypatch.setattr(ctx, "options", options, raising=False)
    return options


def test_parse_pid_accepts_positive_decimal_values():
    assert parse_pid(" 123 ") == 123
    assert parse_pid(123) == 123


@pytest.mark.parametrize("value", ["", "-1", "0", "+1", "1.0", "1\n2", True, 1.0])
def test_parse_pid_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_pid(value)


def test_replace_local_pid_preserves_other_modes_and_listen_suffix():
    assert replace_local_pid(["regular", "local:codex@1234"], 456) == [
        "regular",
        "local:456@1234",
    ]
    assert replace_local_pid(["local@1234"], 789) == ["local:789@1234"]


def test_replace_local_pid_requires_local_mode():
    with pytest.raises(ValueError, match="requires a local proxy mode"):
        replace_local_pid(["regular"], 456)


def test_set_pid_updates_mitmproxy_mode(monkeypatch):
    options = install_fake_options(monkeypatch)
    controller = LinuxLocalPidControl()

    controller._set_pid(456)

    assert options.mode == ["local:456"]
    assert options.updates == [{"mode": ["local:456"]}]
    assert controller._current_pid == 456


def test_set_pid_does_not_update_for_same_pid(monkeypatch):
    options = install_fake_options(monkeypatch)
    options.mode = ["local:456"]
    controller = LinuxLocalPidControl()

    controller._set_pid(456)

    assert options.updates == []
    assert controller._current_pid == 456


def test_linux_controller_is_noop_on_non_linux(monkeypatch):
    install_fake_options(monkeypatch)
    monkeypatch.setattr(linux_pid_control.sys, "platform", "darwin")
    controller = LinuxLocalPidControl()

    asyncio.run(controller.running())

    assert controller._pid_file_task is None
    assert controller._control_server is None


def test_set_pid_is_unavailable_on_non_linux(monkeypatch):
    install_fake_options(monkeypatch)
    monkeypatch.setattr(linux_pid_control.sys, "platform", "darwin")
    controller = LinuxLocalPidControl()

    with pytest.raises(RuntimeError, match="unavailable"):
        controller._set_pid(123)


def test_pid_file_updates_target_and_cleans_watcher(monkeypatch, tmp_path):
    options = install_fake_options(monkeypatch)
    pid_file = tmp_path / "codex.pid"
    pid_file.write_text("123\n", encoding="ascii")
    options.codex_local_pid_file = str(pid_file)
    controller = LinuxLocalPidControl()

    async def scenario():
        await controller.running()
        assert options.mode == ["local:123"]

        pid_file.write_text("456\n", encoding="ascii")
        await asyncio.sleep(0.03)
        assert options.mode == ["local:456"]

        await controller.done()
        assert controller._pid_file_task is None

    asyncio.run(scenario())


def test_control_socket_accepts_pid_and_is_removed_on_shutdown(monkeypatch, tmp_path):
    options = install_fake_options(monkeypatch)
    socket_path = tmp_path / "control.sock"
    options.codex_local_control_socket = str(socket_path)
    controller = LinuxLocalPidControl()

    async def scenario():
        await controller.running()
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        writer.write(b"789\n")
        await writer.drain()
        assert await reader.readline() == b"ok 789\n"
        writer.close()
        await writer.wait_closed()
        assert options.mode == ["local:789"]

        await controller.done()
        assert not socket_path.exists()

    asyncio.run(scenario())


def test_control_socket_refuses_to_replace_regular_file(monkeypatch, tmp_path):
    install_fake_options(monkeypatch)
    socket_path = tmp_path / "control.sock"
    socket_path.write_text("keep me", encoding="utf-8")
    controller = LinuxLocalPidControl()

    async def scenario():
        with pytest.raises(RuntimeError, match="non-socket"):
            await controller._start_control_socket(socket_path)

    asyncio.run(scenario())
