"""Threads, that run in the background, to not lock up the UI."""

import asyncio
from urllib.request import urlopen

import packaging.version
from PySide6.QtCore import QThread, Signal
from yaml import Loader, load

from syng.client import Client
from syng.log import logger


class VersionCheckerWorker(QThread):
    """Get the latest version number of Syng currently on pypi.

    Signals:
        data: Called, as soon as the version data is available. Contains the latest version number
            of Syng
        finished: Called, after version data is send.

    """

    data = Signal(packaging.version.Version)
    finished = Signal()

    def run(self) -> None:
        """Get the latest version from pypi and call the appropriate signals."""
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
    """Start the Syng client in the background.

    Attributes:
        client: Client object
        loop: The async loop, the client runs in

    """

    client: Client | None = None
    loop: asyncio.AbstractEventLoop | None = None

    def cleanup(self) -> None:
        """Terminate the client."""
        logger.debug("Closing the client")
        if self.loop and self.client:
            logger.debug("Closing the client: Found event loop")
            future = asyncio.run_coroutine_threadsafe(self.client.ensure_disconnect(), self.loop)
            future.result(timeout=5)
            self.wait(1000)
            logger.debug("Client closed")

    def export_queue(self, filename: str) -> None:
        """Save the queue of the client to a file.

        Args:
            filename: Path of the file to save to.

        """
        if self.client:
            self.client.export_queue(filename)

    def import_queue(self, filename: str) -> None:
        """Load the queue from a file.

        Args:
            filename: Path of the file to load from.

        """
        if self.loop and self.client:
            asyncio.run_coroutine_threadsafe(self.client.import_queue(filename), self.loop)

    def remove_room(self) -> None:
        """Send a request to remove the current room from the server."""
        if self.loop and self.client:
            asyncio.run_coroutine_threadsafe(self.client.remove_room(), self.loop)

    def set_client(self, client: Client) -> None:
        """Set the client object.

        Args:
            client: The client object to set.

        """
        self.client = client

    def run(self) -> None:
        """Start the client in a new async event loop."""
        if self.client:
            logger.debug("Create new event loop for client")
            self.loop = asyncio.new_event_loop()
            self.loop.run_until_complete(self.client.start_client())
