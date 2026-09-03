"""Linux-only controls for retargeting mitmproxy local capture.

The local redirector accepts a new intercept specification at runtime, but
plain ``mitmdump`` does not expose a command-line control channel.  This
addon provides two small optional control paths for that gap:

* a file containing one PID, polled at a low frequency; and
* a Unix socket which accepts one PID per connection.

Both paths update mitmproxy's public ``mode`` option.  The normal local-mode
server code then updates the existing redirector and keeps its own-process
exclusion intact.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import stat
import sys
from typing import Optional

from mitmproxy import command, ctx, exceptions
from mitmproxy.utils import asyncio_utils


logger = logging.getLogger(__name__)

_MAX_PID = 2**31 - 1
_SOCKET_READ_LIMIT = 128


def parse_pid(value: str | int) -> int:
    """Parse a positive Linux PID."""

    if isinstance(value, bool):
        raise ValueError("PID must be a positive integer")

    if isinstance(value, int):
        pid = value
    elif isinstance(value, str):
        text = value.strip()
        if not text.isdecimal():
            raise ValueError("PID must be a positive integer")
        pid = int(text)
    else:
        raise ValueError("PID must be a positive integer")

    if not 0 < pid <= _MAX_PID:
        raise ValueError("PID must be a positive integer")
    return pid


def replace_local_pid(mode_specs: list[str], pid: int) -> list[str]:
    """Replace the data portion of every local mode with ``pid``."""

    pid = parse_pid(pid)
    replaced: list[str] = []
    found = False

    for spec in mode_specs:
        mode_spec, at, listen_port = spec.rpartition("@")
        if not at:
            mode_spec = spec
            listen_port = ""

        mode = mode_spec.partition(":")[0]
        if mode.lower() != "local":
            replaced.append(spec)
            continue

        found = True
        listen_suffix = f"@{listen_port}" if at else ""
        replaced.append(f"local:{pid}{listen_suffix}")

    if not found:
        raise ValueError("PID control requires a local proxy mode")
    return replaced


class LinuxLocalPidControl:
    """Retarget local capture from a PID file or a Unix control socket."""

    def __init__(self) -> None:
        self._pid_file_task: asyncio.Task | None = None
        self._control_server: asyncio.AbstractServer | None = None
        self._control_socket_path: Path | None = None
        self._control_socket_identity: tuple[int, int] | None = None
        self._current_pid: int | None = None

    def load(self, loader) -> None:
        loader.add_option(
            name="codex_local_pid",
            typespec=Optional[int],
            default=None,
            help="Linux-only PID override for local capture.",
        )
        loader.add_option(
            name="codex_local_pid_file",
            typespec=Optional[str],
            default=None,
            help="Linux-only file containing the PID to select for local capture.",
        )
        loader.add_option(
            name="codex_local_control_socket",
            typespec=Optional[str],
            default=None,
            help="Linux-only Unix socket accepting one target PID per connection.",
        )
        loader.add_option(
            name="codex_local_pid_poll_interval",
            typespec=float,
            default=0.5,
            help="Seconds between Linux local-capture PID-file checks.",
        )

    def configure(self, updated) -> None:
        if sys.platform != "linux" or "codex_local_pid" not in updated:
            return

        pid = ctx.options.codex_local_pid
        if pid is None:
            return

        try:
            self._set_pid(pid)
        except ValueError as exc:
            raise exceptions.OptionsError(str(exc)) from exc

    async def running(self) -> None:
        if sys.platform != "linux":
            return

        poll_interval = ctx.options.codex_local_pid_poll_interval
        if poll_interval <= 0:
            raise exceptions.OptionsError(
                "codex_local_pid_poll_interval must be greater than zero"
            )

        pid_file = self._configured_path(ctx.options.codex_local_pid_file)
        if pid_file is not None:
            await self._apply_pid_file(pid_file)
            self._pid_file_task = asyncio_utils.create_task(
                self._watch_pid_file(pid_file, poll_interval),
                name="codex local PID file watcher",
                keep_ref=False,
            )

        control_socket = self._configured_path(ctx.options.codex_local_control_socket)
        if control_socket is not None:
            await self._start_control_socket(control_socket)

    async def done(self) -> None:
        if self._pid_file_task is not None:
            self._pid_file_task.cancel()
            await asyncio.gather(self._pid_file_task, return_exceptions=True)
            self._pid_file_task = None

        if self._control_server is not None:
            self._control_server.close()
            await self._control_server.wait_closed()
            self._control_server = None

        self._remove_control_socket()

    @command.command("codex.local_pid")
    def local_pid(self, pid: str) -> None:
        """Set the PID selected by Linux local capture."""

        self._set_pid(parse_pid(pid))

    def _set_pid(self, pid: int) -> None:
        if sys.platform != "linux":
            raise RuntimeError("Linux local PID control is unavailable on this platform")

        pid = parse_pid(pid)
        modes = list(ctx.options.mode)
        updated_modes = replace_local_pid(modes, pid)
        if updated_modes == modes:
            self._current_pid = pid
            return

        ctx.options.update(mode=updated_modes)
        self._current_pid = pid
        logger.info("Linux local capture target changed to PID %s", pid)

    async def _apply_pid_file(self, path: Path) -> None:
        try:
            value = path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            return
        except (OSError, UnicodeError) as exc:
            logger.warning("Unable to read local capture PID file %s: %s", path, exc)
            return

        try:
            pid = parse_pid(value)
        except ValueError as exc:
            if value:
                logger.warning("Ignoring invalid local capture PID file %s: %s", path, exc)
            return

        try:
            self._set_pid(pid)
        except (RuntimeError, ValueError, exceptions.OptionsError) as exc:
            logger.warning("Unable to apply local capture PID %s: %s", pid, exc)

    async def _watch_pid_file(self, path: Path, poll_interval: float) -> None:
        last_value: str | None = None
        while True:
            try:
                value = path.read_text(encoding="ascii").strip()
            except FileNotFoundError:
                value = None
            except (OSError, UnicodeError) as exc:
                value = None
                logger.warning("Unable to read local capture PID file %s: %s", path, exc)

            if value != last_value:
                last_value = value
                if value:
                    try:
                        self._set_pid(parse_pid(value))
                    except (RuntimeError, ValueError, exceptions.OptionsError) as exc:
                        logger.warning("Ignoring local capture PID file %s: %s", path, exc)

            await asyncio.sleep(poll_interval)

    async def _start_control_socket(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._remove_stale_socket(path)

        self._control_server = await asyncio.start_unix_server(
            self._handle_control_client,
            path=str(path),
            limit=_SOCKET_READ_LIMIT,
        )
        os.chmod(path, 0o600)
        socket_stat = path.stat()
        self._control_socket_path = path
        self._control_socket_identity = (socket_stat.st_dev, socket_stat.st_ino)
        logger.info("Linux local capture control socket listening at %s", path)

    async def _remove_stale_socket(self, path: Path) -> None:
        try:
            existing = path.lstat()
        except FileNotFoundError:
            return

        if not stat.S_ISSOCK(existing.st_mode):
            raise RuntimeError(f"Refusing to replace non-socket path: {path}")

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(path)), timeout=0.2
            )
        except (ConnectionRefusedError, FileNotFoundError, asyncio.TimeoutError, OSError):
            path.unlink()
            return
        else:
            del reader
            writer.close()
            await writer.wait_closed()
            raise RuntimeError(f"Control socket is already in use: {path}")

    async def _handle_control_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw_value = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not raw_value:
                raise ValueError("empty PID request")
            pid = parse_pid(raw_value.decode("ascii"))
            self._set_pid(pid)
            response = f"ok {pid}\n"
        except (UnicodeError, ValueError, RuntimeError, exceptions.OptionsError) as exc:
            response = f"error {exc}\n"
        except asyncio.TimeoutError:
            response = "error timed out waiting for PID\n"
        except OSError:
            response = "error control connection failed\n"

        try:
            writer.write(response.encode("utf-8"))
            await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    def _remove_control_socket(self) -> None:
        path = self._control_socket_path
        identity = self._control_socket_identity
        self._control_socket_path = None
        self._control_socket_identity = None
        if path is None or identity is None:
            return

        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) != identity:
            logger.warning("Not removing replaced control socket path %s", path)
            return
        if stat.S_ISSOCK(current.st_mode):
            path.unlink()

    @staticmethod
    def _configured_path(value: str | None) -> Path | None:
        if not value:
            return None
        return Path(value).expanduser().absolute()


addons = [LinuxLocalPidControl()]
