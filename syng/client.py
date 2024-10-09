"""
Module for the playback client.

The client connects to the server via the socket.io protocol, and plays the
songs, that are sent by the server.

Playback is done by the :py:class:`syng.sources.source.Source` objects, that
are configured in the `sources` section of the configuration file and can currently
be one of:
  - `youtube`
  - `s3`
  - `files`
"""

from __future__ import annotations
import os
import asyncio
import datetime
from logging import LogRecord
from logging.handlers import QueueHandler
from multiprocessing import Queue
import secrets
import string
import tempfile
import signal
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from traceback import print_exc
from typing import Any, Optional

from qrcode.main import QRCode

import socketio
from socketio.exceptions import ConnectionError
import engineio
from PIL import Image
from yaml import load, Loader

from . import jsonencoder
from .entry import Entry
from .sources import configure_sources, Source
from .log import logger


def default_config() -> dict[str, Optional[int | str]]:
    """
    Return a default configuration for the client.

    :returns: A dictionary with the default configuration.
    :rtype: dict[str, Optional[int | str]]
    """
    return {
        "server": "https://syng.rocks",
        "room": "",
        "preview_duration": 3,
        "secret": None,
        "last_song": None,
        "waiting_room_policy": None,
        "key": None,
        "mpv_options": "",
        "show_advanced": False,
    }


@dataclass
class State:
    """This captures the current state of the playback client.

    It doubles as a backup of the state of the :py:class:`syng.server` in case
    the server needs to be restarted.

    :param current_source: This holds a reference to the
        :py:class:`syng.sources.source.Source` object, that is currently
        playing. If no song is played, the value is `None`.
    :type current_source: Optional[Source]
    :param queue: A copy of the current playlist on the server.
    :type queue: list[Entry]
    :param waiting_room: A copy of the waiting room on the server.
    :type waiting_room: list[Entry]
    :param recent: A copy of all played songs this session.
    :type recent: list[Entry]
    :param config: Various configuration options for the client:
        * `server` (`str`): The url of the server to connect to.
        * `room` (`str`): The room on the server this playback client is connected to.
        * `secret` (`str`): The passcode of the room. If a playback client reconnects to
            a room, this must be identical. Also, if a webclient wants to have
            admin privileges, this must be included.
        * `key` (`Optional[str]`) An optional key, if registration or functionality on the server
            is limited.
        * `preview_duration` (`Optional[int]`): The duration in seconds the
            playback client shows a preview for the next song. This is accounted for
            in the calculation of the ETA for songs later in the queue.
        * `last_song` (`Optional[datetime.datetime]`): A timestamp, defining the end of
            the queue.
        * `waiting_room_policy` (Optional[str]): One of:
            - `forced`, if a performer is already in the queue, they are put in the
                       waiting room.
            - `optional`, if a performer is already in the queue, they have the option
                          to be put in the waiting room.
            - `None`, performers are always added to the queue.
    :type config: dict[str, Any]:
    """

    # pylint: disable=too-many-instance-attributes

    current_source: Optional[Source] = None
    queue: list[Entry] = field(default_factory=list)
    waiting_room: list[Entry] = field(default_factory=list)
    recent: list[Entry] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=default_config)


# state: State = State()


class Client:
    def __init__(self, config: dict[str, Any]):
        self.sio = socketio.AsyncClient(json=jsonencoder)
        self.config = config
        self.sources = configure_sources(config["sources"])
        self.state = State()
        self.currentLock = asyncio.Semaphore(0)
        self.register_handlers()

    def register_handlers(self) -> None:
        self.sio.on("update_config", self.handle_update_config)
        self.sio.on("skip-current", self.handle_skip_current)
        self.sio.on("state", self.handle_state)
        self.sio.on("connect", self.handle_connect)
        self.sio.on("get-meta-info", self.handle_get_meta_info)
        self.sio.on("play", self.handle_play)
        self.sio.on("search", self.handle_search)
        self.sio.on("client-registered", self.handle_client_registered)
        self.sio.on("request-config", self.handle_request_config)

    async def handle_update_config(self, data: dict[str, Any]) -> None:
        """
        Handle the "update_config" message.

        Currently, this function is untested and should be considered dangerous.

        :param data: A dictionary with the new configuration.
        :type data: dict[str, Any]
        :rtype: None
        """
        self.state.config = default_config() | data

    async def handle_skip_current(self, data: dict[str, Any]) -> None:
        """
        Handle the "skip-current" message.

        Skips the song, that is currently played. If playback currently waits for
        buffering, the buffering is also aborted.

        Since the ``queue`` could already be updated, when this evaluates, the
        first entry in the queue is send explicitly.

        :param data: An entry, that should be equivalent to the first entry of the
            queue.
        :rtype: None
        """
        logger.info("Skipping current")
        if self.state.current_source is not None:
            await self.state.current_source.skip_current(Entry(**data))

    async def handle_state(self, data: dict[str, Any]) -> None:
        """
        Handle the "state" message.

        The "state" message forwards the current queue and recent list from the
        server. This function saves a copy of both in the global
        :py:class:`State`:.

        After recieving the new state, a buffering task for the first elements of
        the queue is started.

        :param data: A dictionary with the `queue` and `recent` list.
        :type data: dict[str, Any]
        :rtype: None
        """
        self.state.queue = [Entry(**entry) for entry in data["queue"]]
        self.state.waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
        self.state.recent = [Entry(**entry) for entry in data["recent"]]

        for entry in self.state.queue[:2]:
            logger.info("Buffering: %s", entry.title)
            await self.sources[entry.source].buffer(entry)

    async def handle_connect(self) -> None:
        """
        Handle the "connect" message.

        Called when the client successfully connects or reconnects to the server.
        Sends a `register-client` message to the server with the initial state and
        configuration of the client, consiting of the currently saved
        :py:attr:`State.queue` and :py:attr:`State.recent` field of the global
        :py:class:`State`, as well a room code the client wants to connect to, a
        secret to secure the access to the room and a config dictionary.

        If the room code is `None`, the server will issue a room code.

        This message will be handled by the
        :py:func:`syng.server.handle_register_client` function of the server.

        :rtype: None
        """
        logger.info("Connected to server")
        data = {
            "queue": self.state.queue,
            "waiting_room": self.state.waiting_room,
            "recent": self.state.recent,
            "config": self.state.config,
        }
        await self.sio.emit("register-client", data)

    async def handle_get_meta_info(self, data: dict[str, Any]) -> None:
        """
        Handle a "get-meta-info" message.

        Collects the metadata for a given :py:class:`Entry`, from its source, and
        sends them back to the server in a "meta-info" message. On the server side
        a :py:func:`syng.server.handle_meta_info` function is called.

        :param data: A dictionary encoding the entry
        :type data: dict[str, Any]
        :rtype: None
        """
        source: Source = self.sources[data["source"]]
        meta_info: dict[str, Any] = await source.get_missing_metadata(Entry(**data))
        await self.sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})

    async def preview(self, entry: Entry) -> None:
        """
        Generate and play a preview for a given :py:class:`Entry`.

        This function shows a black screen and prints the artist, title and
        performer of the entry for a duration.

        This is done by creating a black png file, and showing subtitles in the
        middle of the screen.... don't ask, it works

        :param entry: The entry to preview
        :type entry: :py:class:`Entry`
        :rtype: None
        """
        background = Image.new("RGB", (1280, 720))
        subtitle: str = f"""1
00:00:00,00 --> 00:05:00,00
{entry.artist} - {entry.title}
{entry.performer}"""
        with tempfile.NamedTemporaryFile() as tmpfile:
            background.save(tmpfile, "png")
            process = await asyncio.create_subprocess_exec(
                "mpv",
                tmpfile.name,
                f"--image-display-duration={self.state.config['preview_duration']}",
                "--sub-pos=50",
                "--sub-file=-",
                "--fullscreen",
                self.state.config["mpv_options"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate(subtitle.encode())

    async def handle_play(self, data: dict[str, Any]) -> None:
        """
        Handle the "play" message.

        Plays the :py:class:`Entry`, that is encoded in the `data` parameter. If a
        :py:attr:`State.preview_duration` is set, it shows a small preview before
        that.

        When the playback is done, the next song is requested from the server with
        a "pop-then-get-next" message. This is handled by the
        :py:func:`syng.server.handle_pop_then_get_next` function on the server.

        If the entry is marked as skipped, emit a "get-first"  message instead,
        because the server already handled the removal of the first entry.

        :param data: A dictionary encoding the entry
        :type data: dict[str, Any]
        :rtype: None
        """
        entry: Entry = Entry(**data)
        print(
            f"Playing: {entry.artist} - {entry.title} [{entry.album}] "
            f"({entry.source}) for {entry.performer}"
        )
        try:
            self.state.current_source = self.sources[entry.source]
            if self.state.config["preview_duration"] > 0:
                await self.preview(entry)
            await self.sources[entry.source].play(entry, self.state.config["mpv_options"])
        except Exception:  # pylint: disable=broad-except
            print_exc()
        self.state.current_source = None
        if entry.skip:
            await self.sio.emit("get-first")
        else:
            await self.sio.emit("pop-then-get-next")

    async def handle_search(self, data: dict[str, Any]) -> None:
        """
        Handle the "search" message.

        This handles client side search requests. It sends a search request to all
        configured :py:class:`syng.sources.source.Source` and collects the results.

        The results are then send back to the server in a "search-results" message,
        including the `sid` of the corresponding webclient.

        :param data: A dictionary with the `query` and `sid` entry.
        :type data: dict[str, Any]
        :rtype: None
        """
        logger.info(f"Searching for: {data['query']}")
        query = data["query"]
        sid = data["sid"]
        results_list = await asyncio.gather(
            *[source.search(query) for source in self.sources.values()]
        )

        results = [
            search_result.to_dict()
            for source_result in results_list
            for search_result in source_result
        ]

        await self.sio.emit("search-results", {"results": results, "sid": sid})

    async def handle_client_registered(self, data: dict[str, Any]) -> None:
        """
        Handle the "client-registered" message.

        If the registration was successfull (`data["success"]` == `True`), store
        the room code in the global :py:class:`State` and print out a link to join
        the webclient.

        Start listing all configured :py:class:`syng.sources.source.Source` to the
        server via a "sources" message. This message will be handled by the
        :py:func:`syng.server.handle_sources` function and may request additional
        configuration for each source.

        If there is no song playing, start requesting the first song of the queue
        with a "get-first" message. This will be handled on the server by the
        :py:func:`syng.server.handle_get_first` function.

        :param data: A dictionary containing a `success` and a `room` entry.
        :type data: dict[str, Any]
        :rtype: None
        """
        if data["success"]:
            logger.info("Registered")

            # this is borked on windows
            if os.name != "nt":
                print(f"Join here: {self.state.config['server']}/{data['room']}")
                qr = QRCode(box_size=20, border=2)
                qr.add_data(f"{self.state.config['server']}/{data['room']}")
                qr.make()
                qr.print_ascii()
            self.state.config["room"] = data["room"]
            await self.sio.emit("sources", {"sources": list(self.sources.keys())})
            if self.state.current_source is None:  # A possible race condition can occur here
                await self.sio.emit("get-first")
        else:
            logger.warning("Registration failed")
            await self.sio.disconnect()

    async def handle_request_config(self, data: dict[str, Any]) -> None:
        """
        Handle the "request-config" message.

        Sends the specific server side configuration for a given
        :py:class:`syng.sources.source.Source`.

        A Source can decide, that the config will be split up in multiple Parts.
        If this is the case, multiple "config-chunk" messages will be send with a
        running enumerator. Otherwise a single "config" message will be send.

        After the configuration is send, the source is asked to update its
        configuration. This can also be split up in multiple parts.

        :param data: A dictionary with the entry `source` and a string, that
            corresponds to the name of a source.
        :type data: dict[str, Any]
        :rtype: None
        """
        if data["source"] in self.sources:
            config: dict[str, Any] | list[dict[str, Any]] = await self.sources[
                data["source"]
            ].get_config()
            if isinstance(config, list):
                num_chunks: int = len(config)
                for current, chunk in enumerate(config):
                    await self.sio.emit(
                        "config-chunk",
                        {
                            "source": data["source"],
                            "config": chunk,
                            "number": current,
                            "total": num_chunks,
                        },
                    )
            else:
                await self.sio.emit("config", {"source": data["source"], "config": config})

            updated_config = await self.sources[data["source"]].update_config()
            if isinstance(updated_config, list):
                num_chunks = len(updated_config)
                for current, chunk in enumerate(updated_config):
                    await self.sio.emit(
                        "config-chunk",
                        {
                            "source": data["source"],
                            "config": chunk,
                            "number": current,
                            "total": num_chunks,
                        },
                    )
            elif updated_config is not None:
                await self.sio.emit("config", {"source": data["source"], "config": updated_config})

    def signal_handler(self) -> None:
        """
        Signal handler for the client.

        This function is called when the client receives a signal to terminate. It
        will disconnect from the server and kill the current player.

        :rtype: None
        """
        engineio.async_client.async_signal_handler()
        if self.state.current_source is not None:
            if self.state.current_source.player is not None:
                self.state.current_source.player.kill()

    async def start_client(self, config: dict[str, Any]) -> None:
        """
        Initialize the client and connect to the server.

        :param config: Config options for the client
        :type config: dict[str, Any]
        :rtype: None
        """

        self.sources.update(configure_sources(config["sources"]))

        if "config" in config:
            last_song = (
                datetime.datetime.fromisoformat(config["config"]["last_song"]).timestamp()
                if "last_song" in config["config"] and config["config"]["last_song"]
                else None
            )
            self.state.config |= config["config"] | {"last_song": last_song}

        if not ("secret" in self.state.config and self.state.config["secret"]):
            self.state.config["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )
            print(f"Generated secret: {self.state.config['secret']}")

        if not ("key" in self.state.config and self.state.config["key"]):
            self.state.config["key"] = ""

        try:
            await self.sio.connect(self.state.config["server"])
        except ConnectionError:
            logger.error("Could not connect to server")
            return

        # this is not supported under windows
        if os.name != "nt":
            asyncio.get_event_loop().add_signal_handler(signal.SIGINT, self.signal_handler)
            asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, self.signal_handler)

        try:
            await self.sio.wait()
        except asyncio.CancelledError:
            pass
        finally:
            if self.state.current_source is not None:
                if self.state.current_source.player is not None:
                    self.state.current_source.player.kill()


def create_async_and_start_client(
    config: dict[str, Any], queue: Optional[Queue[LogRecord]] = None
) -> None:
    """
    Create an asyncio event loop and start the client.

    If a multiprocessing queue is given, the client will log to the queue.

    :param config: Config options for the client
    :type config: dict[str, Any]
    :param queue: A multiprocessing queue to log to
    :type queue: Optional[Queue[LogRecord]]
    :rtype: None
    """

    if queue is not None:
        logger.addHandler(QueueHandler(queue))

    client = Client(config)

    asyncio.run(client.start_client(config))


def run_client(args: Namespace) -> None:
    """
    Run the client with the given arguments.

    Namespace contains the following attributes:
        - room: The room code to connect to
        - secret: The secret to connect to the room
        - config_file: The path to the configuration file
        - key: The key to connect to the server
        - server: The url of the server to connect to

    :param args: The arguments from the command line
    :type args: Namespace
    :rtype: None
    """
    try:
        with open(args.config_file, encoding="utf8") as file:
            config = load(file, Loader=Loader)
    except FileNotFoundError:
        config = {}

    if "config" not in config:
        config["config"] = {}

    if args.room:
        config["config"] |= {"room": args.room}
    if args.secret:
        config["config"] |= {"secret": args.secret}
    if args.server:
        config["config"] |= {"server": args.server}

    create_async_and_start_client(config)
