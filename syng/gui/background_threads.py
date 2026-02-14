import asyncio
from typing import Any
from urllib.request import urlopen

import packaging.version
from PySide6.QtCore import QThread, Signal
from yaml import Loader, load

from syng.client import Client
from syng.log import logger


class VersionCheckerWorker(QThread):
    data = Signal(packaging.version.Version)
    finished = Signal()

    def run(self) -> None:
        with urlopen("https://pypi.org/pypi/syng/json") as response:
            if response.status == 200:
                data = load(response.read(), Loader=Loader)
                versions = filter(
                    lambda v: not v.is_prerelease,
                    map(packaging.version.parse, data["releases"].keys()),
                )
                self.data.emit(max(versions))
        self.finished.emit()


class SyngClientWorker(QThread):
    def __init__(self, client: Client) -> None:
        super().__init__()
        self.client = client
        self.config: dict[str, Any] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def cleanup(self) -> None:
        logger.debug("Closing the client")
        if self.loop is not None:
            logger.debug("Closing the client: Found event loop")
            future = asyncio.run_coroutine_threadsafe(self.client.ensure_disconnect(), self.loop)
            future.result(timeout=5)
            self.wait(1000)
            logger.debug("Client closed")

    def export_queue(self, filename: str) -> None:
        self.client.export_queue(filename)

    def import_queue(self, filename: str) -> None:
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self.client.import_queue(filename), self.loop)

    def remove_room(self) -> None:
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self.client.remove_room(), self.loop)

    def set_config(self, config: dict[str, Any]) -> None:
        self.config = config

    def run(self) -> None:
        logger.debug("Create new event loop for client")
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.client.start_client(self.config))
