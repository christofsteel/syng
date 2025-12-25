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
from collections.abc import Callable
from functools import partial
import logging
import os
import asyncio
import datetime
from logging import LogRecord
from logging.handlers import QueueHandler
from multiprocessing import Queue
import secrets
import string
import signal
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from traceback import print_exc
from typing import Any, Optional
from uuid import UUID

from qrcode.main import QRCode

import socketio
from socketio.exceptions import ConnectionError, BadNamespaceError
import engineio
from yaml import load, Loader

from syng.player_libmpv import Player

from . import SYNG_VERSION, jsonencoder
from .entry import Entry
from .sources import configure_sources, Source
from .log import logger


class ConnectionState:
    __is_connected__ = False
    __mpv_running__ = False

    def is_connected(self) -> bool:
        return self.__is_connected__

    def is_mpv_running(self) -> bool:
        return self.__mpv_running__

    def set_disconnected(self) -> None:
        self.__is_connected__ = False

    def set_connected(self) -> None:
        self.__is_connected__ = True

    def set_mpv_running(self) -> None:
        self.__mpv_running__ = True

    def set_mpv_terminated(self) -> None:
        self.__mpv_running__ = False


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
        "buffer_in_advance": 2,
        "qr_box_size": 7,
        "qr_position": "top-right",
        "show_advanced": False,
        "log_level": "info",
        "next_up_time": 20,
        "allow_collab_mode": True,
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
        * `next_up_position` (`str`): The position of the "next up" box on the screen.
            Possible values are: top or bottom.
        * `last_song` (`Optional[datetime.datetime]`): A timestamp, defining the end of
            the queue.
        * `waiting_room_policy` (Optional[str]): One of:
            - `forced`, if a performer is already in the queue, they are put in the
                       waiting room.
            - `optional`, if a performer is already in the queue, they have the option
                          to be put in the waiting room.
            - `None`, performers are always added to the queue.
        * `allow_collab_mode` (`bool`): If False, does not allow for collab_mode selection in webui
        * `buffer_in_advance` (`int`): The number of songs, that are buffered in
            advance.
        * `qr_box_size` (`int`): The size of one box in the QR code.
        * `qr_position` (`str`): The position of the QR code on the screen. One of:
            - `top-left`
            - `top-right`
            - `bottom-left`
            - `bottom-right`
        * `show_advanced` (`bool`): If the advanced options should be shown in the
            gui.
        * `log_level` (`str`): The log level of the client. One of: `debug`, `info`, `warning`,
            `error`, `critical`. Default is `info`.

    :type config: dict[str, Any]:
    """

    # pylint: disable=too-many-instance-attributes

    current_source: Optional[Source] = None
    queue: list[Entry] = field(default_factory=list)
    waiting_room: list[Entry] = field(default_factory=list)
    recent: list[Entry] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=default_config)
    old_config: dict[str, Any] = field(default_factory=default_config)


class Client:
    def __init__(self, config: dict[str, Any]):
        config["config"] = default_config() | config["config"]

        self.connection_event = asyncio.Event()
        self.connection_state = ConnectionState()
        self.set_log_level(config["config"]["log_level"])
        self.sio = socketio.AsyncClient(json=jsonencoder, reconnection_attempts=-1)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.skipped: list[UUID] = []
        self.sources = configure_sources(config["sources"])
        self.state = State()
        self.currentLock = asyncio.Semaphore(0)
        self.buffer_in_advance = config["config"]["buffer_in_advance"]
        self.player = Player(
            config["config"],
            self.quit_callback,
            self.state.queue,
        )
        self.connection_state.set_mpv_running()
        logger.debug(f"MPV running: {self.connection_state.is_mpv_running()} ")
        self.register_handlers()
        self.queue_callbacks: list[Callable[[list[Entry]], None]] = []

    def add_queue_callback(self, callback: Callable[[list[Entry]], None]) -> None:
        self.queue_callbacks.append(callback)

    def set_log_level(self, level: str) -> None:
        match level:
            case "debug":
                logger.setLevel(logging.DEBUG)
            case "info":
                logger.setLevel(logging.INFO)
            case "warning":
                logger.setLevel(logging.WARNING)
            case "error":
                logger.setLevel(logging.ERROR)
            case "critical":
                logger.setLevel(logging.CRITICAL)

    def register_handlers(self) -> None:
        self.sio.on("update_config", self.handle_update_config)
        self.sio.on("skip-current", self.handle_skip_current)
        self.sio.on("state", self.handle_state)
        self.sio.on("connect", self.handle_connect)
        self.sio.on("get-meta-info", self.handle_get_meta_info)
        self.sio.on("play", self.handle_play)
        self.sio.on("search", self.handle_search)
        self.sio.on("request-config", self.handle_request_config)
        self.sio.on("msg", self.handle_msg)
        self.sio.on("disconnect", self.handle_disconnect)
        self.sio.on("room-removed", self.handle_room_removed)
        self.sio.on("*", self.handle_unknown_message)
        self.sio.on("connect_error", self.handle_connect_error)

    async def handle_connect_error(self, data: dict[str, Any]) -> None:
        """
        Handle the "connect_error" message.

        This function is called when the client fails to connect to the server.
        It will log the error and disconnect from the server.

        :param data: A dictionary with the error message.
        :type data: dict[str, Any]
        :rtype: None
        """
        logger.critical("Connection error: %s", data["message"])
        await self.ensure_disconnect()

    async def handle_unknown_message(self, event: str, data: dict[str, Any]) -> None:
        """
        Handle unknown messages.

        This function is called when the client receives a message, that is not
        handled by any of the other handlers. It will log the event and data.

        :param event: The name of the event
        :type event: str
        :param data: The data of the event
        :type data: dict[str, Any]
        :rtype: None
        """
        logger.warning(f"Unknown message: {event} with data: {data}")

    async def handle_disconnect(self) -> None:
        self.connection_state.set_disconnected()
        await self.ensure_disconnect()

    async def ensure_disconnect(self) -> None:
        """
        Ensure that the client is disconnected from the server and the player is
        terminated.
        """
        logger.info("Disconnecting from server")
        logger.debug(f"Connection: {self.connection_state.is_connected()}")
        logger.debug(f"MPV running: {self.connection_state.is_mpv_running()}")
        if self.connection_state.is_connected():
            await self.sio.disconnect()
        if self.connection_state.is_mpv_running():
            if self.player.mpv is not None:
                self.player.mpv.terminate()

    async def handle_msg(self, data: dict[str, Any]) -> None:
        """
        Handle the "msg" message.

        This function is used to print messages from the server to the console.

        :param data: A dictionary with the `msg` entry.
        :type data: dict[str, Any]
        :rtype: None
        """

        msg_type = data.get("type", "info")
        match msg_type:
            case "debug":
                logger.debug(data["msg"])
            case "info":
                logger.info(data["msg"])
            case "warning":
                logger.warning(data["msg"])
            case "error":
                logger.error(data["msg"])
            case "critical":
                logger.critical(data["msg"])

    async def handle_update_config(self, data: dict[str, Any]) -> None:
        """
        Handle the "update_config" message.

        Currently, this function is untested and should be considered dangerous.

        :param data: A dictionary with the new configuration.
        :type data: dict[str, Any]
        :rtype: None
        """
        self.state.config = default_config() | data

    async def send_update_config(self) -> None:
        """
        Send the current configuration to the server.

        This is used to update the server with the current configuration of the
        client. This is done by sending a "update_config" message to the server.

        :rtype: None
        """

        changes = dict()
        for key, value in self.state.config.items():
            if key in default_config() and default_config()[key] != value:
                changes[key] = value

        await self.sio.emit("update_config", self.state.config)

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
        self.skipped.append(data["uuid"])

        entry = Entry(**data)
        logger.info("Skipping: %s", entry.title)
        source = self.sources[entry.source]

        await source.skip_current(Entry(**data))
        self.player.skip_current()

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
        await self.connection_event.wait()
        self.state.queue.clear()
        self.state.queue.extend([Entry(**entry) for entry in data["queue"]])
        self.state.waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
        self.state.recent = [Entry(**entry) for entry in data["recent"]]

        for pos, entry in enumerate(self.state.queue[0 : self.buffer_in_advance]):
            source = self.sources[entry.source]
            if entry.incomplete_data:
                meta_info = await source.get_missing_metadata(entry)
                await self.sio.emit("meta-info", {"uuid": entry.uuid, "meta": meta_info})
                entry.update(**meta_info)

            if entry.ident in source.downloaded_files:
                continue
            logger.info("Buffering: %s (%d s)", entry.title, entry.duration)
            started = datetime.datetime.now()
            try:
                await self.sources[entry.source].buffer(entry, pos)
                logger.info(
                    "Buffered %s in %d seconds",
                    entry.title,
                    (datetime.datetime.now() - started).seconds,
                )
            except ValueError as e:
                logger.error("Error buffering: %s", e)
                await self.sio.emit("skip", {"uuid": entry.uuid})
        for callback in self.queue_callbacks:
            callback(self.state.queue)

    async def handle_connect(self) -> None:
        """
        Handle the "connect" message.

        This is called when the client successfully connects to the server
        and starts the player.

        Start listing all configured :py:class:`syng.sources.source.Source` to the
        server via a "sources" message. This message will be handled by the
        :py:func:`syng.server.handle_sources` function and may request additional
        configuration for each source.

        If there is no song playing, start requesting the first song of the queue
        with a "get-first" message. This will be handled on the server by the
        :py:func:`syng.server.handle_get_first` function.

        :rtype: None
        """
        logger.info("Connected to server: %s", self.state.config["server"])
        self.player.start()
        room = self.state.config["room"]
        server = self.state.config["server"]

        logger.info("Connected to room: %s", room)
        qr_string = f"{server}/{room}"
        self.player.update_qr(qr_string)
        # this is borked on windows

        if os.name != "nt":
            print(f"Join here: {server}/{room}")
            qr = QRCode(box_size=20, border=2)
            qr.add_data(qr_string)
            qr.make()
            qr.print_ascii()

        await self.sio.emit("sources", {"sources": list(self.sources.keys())})
        if self.state.current_source is None:  # A possible race condition can occur here
            await self.sio.emit("get-first")
        self.connection_event.set()
        self.connection_state.set_connected()

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
        await self.player.queue_next(entry)

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
        source = self.sources[entry.source]
        print(
            f"Playing: {entry.artist} - {entry.title} [{entry.album}] "
            f"({entry.source}) for {entry.performer}"
        )
        logger.info(
            "Playing: %s - %s [%s] (%s) for %s",
            entry.artist,
            entry.title,
            entry.album,
            entry.source,
            entry.performer,
        )
        if entry.uuid not in self.skipped:
            try:
                if self.state.config["preview_duration"] > 0:
                    await self.preview(entry)
                video, audio = await source.ensure_playable(entry)
                if entry.uuid not in self.skipped:
                    self.skipped = []
                    await self.player.play(video, audio, source.extra_mpv_options)
            except ValueError as e:
                logger.error("Error playing: %s", e)
                self.skipped.append(entry.uuid)
            except Exception:  # pylint: disable=broad-except
                print_exc()
        if self.skipped:
            self.skipped.remove(entry.uuid)
            await self.sio.emit("get-first")
        else:
            try:
                await self.sio.emit("pop-then-get-next")
            except BadNamespaceError:
                pass

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
        logger.debug("Handling search: %s (%s)", data["query"], data["search_id"])
        query = data["query"]
        sid = data["sid"]
        search_id = data["search_id"]
        results_list = await asyncio.gather(
            *[source.search(query) for source in self.sources.values()]
        )

        results = [
            search_result.to_dict()
            for source_result in results_list
            for search_result in source_result
        ]
        logger.debug("Search results: %d results", len(results))

        await self.sio.emit(
            "search-results", {"results": results, "sid": sid, "search_id": search_id}
        )

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
        await self.connection_event.wait()
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
                    await asyncio.sleep(0.1)  # Avoiding qasync errors
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

    def signal_handler(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Signal handler for the client.

        This function is called when the client receives a signal to terminate. It
        will disconnect from the server and kill the current player.

        :param loop: The asyncio event loop
        :type loop: asyncio.AbstractEventLoop
        :rtype: None
        """
        engineio.async_client.async_signal_handler()
        asyncio.ensure_future(self.ensure_disconnect(), loop=loop)

    def quit_callback(self) -> None:
        """
        Callback function for the player, terminating the player and disconnecting

        :rtype: None
        """
        self.connection_state.set_mpv_terminated()
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self.ensure_disconnect(), self.loop)
            asyncio.run_coroutine_threadsafe(self.kill_mpv(), self.loop)

    async def kill_mpv(self) -> None:
        """
        Kill the mpv process. Needs to be called in a seperate thread, because of mpv...
        See https://github.com/jaseg/python-mpv/issues/114#issuecomment-1214305952

        :rtype: None
        """
        if self.player.mpv is not None:
            self.player.mpv.terminate()

    async def remove_room(self) -> None:
        """
        Remove the room from the server.
        """

        if self.state.config["room"] is not None:
            logger.info("Removing room %s from server", self.state.config["room"])
            await self.sio.emit("remove-room", {"room": self.state.config["room"]})

    def export_queue(self, filename: str) -> None:
        """
        Export the current queue to a file.

        :param filename: The name of the file to export the queue to.
        :type filename: str
        :rtype: None
        """
        with open(filename, "w", encoding="utf8") as file:
            jsonencoder.dump(
                {
                    "queue": self.state.queue,
                    "waiting_room": self.state.waiting_room,
                    "recent": self.state.recent,
                },
                file,
                indent=2,
                ensure_ascii=False,
            )

    async def import_queue(self, filename: str) -> None:
        """
        Import a queue from a file.

        :param filename: The name of the file to import the queue from.
        :type filename: str
        :rtype: None
        """
        with open(filename, "r", encoding="utf8") as file:
            data = jsonencoder.load(file)
            queue = [Entry(**entry) for entry in data["queue"]]
            waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
            recent = [Entry(**entry) for entry in data["recent"]]
            await self.sio.emit(
                "import-queue", {"queue": queue, "waiting_room": waiting_room, "recent": recent}
            )

    async def handle_room_removed(self, data: dict[str, Any]) -> None:
        """
        Handle the "room-removed" message.

        This is called when the server removes the room, that this client is
        connected to. We simply log this event.

        :param data: A dictionary with the `room` entry.
        :type data: dict[str, Any]
        :rtype: None
        """
        logger.info("Room removed: %s", data["room"])

    async def start_client(self, config: dict[str, Any]) -> None:
        """
        Initialize the client and connect to the server.

        :param config: Config options for the client
        :type config: dict[str, Any]
        :rtype: None
        """

        self.loop = asyncio.get_running_loop()

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
            data = {
                "type": "playback",
                "queue": self.state.queue,
                "waiting_room": self.state.waiting_room,
                "recent": self.state.recent,
                "config": self.state.config,
                "version": SYNG_VERSION,
            }
            await self.sio.connect(self.state.config["server"], auth=data)

            # this is not supported under windows
            if os.name != "nt":
                loop = asyncio.get_event_loop()
                loop.add_signal_handler(signal.SIGINT, partial(self.signal_handler, loop))

            await self.sio.wait()
        except asyncio.CancelledError:
            pass
        except ConnectionError as e:
            logger.warning("Could not connect to server: %s", e.args[0])
        finally:
            await self.ensure_disconnect()


def create_async_and_start_client(
    config: dict[str, Any],
    queue: Optional[Queue[LogRecord]] = None,
    client: Optional[Client] = None,
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

    if client is None:
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

    if "sources" not in config:
        config["sources"] = {"youtube": {"enabled": True}}

    if args.room:
        config["config"] |= {"room": args.room}
    if args.secret:
        config["config"] |= {"secret": args.secret}
    if args.server:
        config["config"] |= {"server": args.server}

    create_async_and_start_client(config)
