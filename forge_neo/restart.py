from __future__ import annotations

import logging
import threading
import time
from typing import Optional


log = logging.getLogger(__name__)


class ForgeNeoServerState:
    def __init__(self) -> None:
        self.server_start = time.time()
        self._server_command_signal = threading.Event()
        self._server_command: Optional[str] = None
        self.interrupted = False

    @property
    def need_restart(self) -> bool:
        return self.server_command == "restart"

    @need_restart.setter
    def need_restart(self, value: bool) -> None:
        if value:
            self.server_command = "restart"

    @property
    def server_command(self) -> Optional[str]:
        return self._server_command

    @server_command.setter
    def server_command(self, value: Optional[str]) -> None:
        self._server_command = value
        self._server_command_signal.set()

    def wait_for_server_command(self, timeout: Optional[float] = None) -> Optional[str]:
        if self._server_command_signal.wait(timeout):
            self._server_command_signal.clear()
            command = self._server_command
            self._server_command = None
            return command
        return None

    def interrupt(self) -> None:
        self.interrupted = True
        log.info("Received interrupt request")

    def request_restart(self) -> None:
        self.interrupt()
        self.server_command = "restart"
        log.info("Received Forge Neo UI reload request")

    def request_stop(self) -> None:
        self.server_command = "stop"
        log.info("Received Forge Neo stop request")

    def request_kill(self) -> None:
        self.server_command = "kill"
        log.info("Received Forge Neo kill request")


def ensure_server_state() -> ForgeNeoServerState:
    import shared

    current = getattr(shared, "state", None)
    if current is not None and all(hasattr(current, name) for name in ("request_restart", "wait_for_server_command")):
        return current

    state = ForgeNeoServerState()
    shared.state = state
    return state
