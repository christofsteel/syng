"""
Module for the playback client.

Excerp from the help::

    usage: client.py [-h] [--room ROOM] [--secret SECRET] \
            [--config-file CONFIG_FILE] [--server server]

    options:
      -h, --help            show this help message and exit
      --room ROOM, -r ROOM 
      --secret SECRET, -s SECRET
      --config-file CONFIG_FILE, -C CONFIG_FILE
      --key KEY, -k KEY
      --server

The config file should be a yaml file in the following style::

      sources:
        SOURCE1:  
          configuration for SOURCE
        SOURCE2: 
          configuration for SOURCE
        ...
      config:
        server: ...
        room: ...
        preview_duration: ...
        secret: ...
        last_song: ...
        waiting_room_policy: ..

"""

import asyncio
import datetime
import logging
import os
import secrets
import string
import tempfile
import signal
from argparse import ArgumentParser
from dataclasses import dataclass
from dataclasses import field
from traceback import print_exc
from typing import Any, Optional
import platformdirs

from qrcode.main import QRCode

import socketio
import engineio
from PIL import Image
from yaml import load, Loader

from . import jsonencoder
from .entry import Entry
from .sources import configure_sources, Source


sio: socketio.AsyncClient = socketio.AsyncClient(json=jsonencoder)
logger: logging.Logger = logging.getLogger(__name__)
sources: dict[str, Source] = {}


currentLock: asyncio.Semaphore = asyncio.Semaphore(0)


def default_config() -> dict[str, Optional[int | str]]:
    return {
        "server": "http://localhost:8080",
        "room": "ABCD",
        "preview_duration": 3,
        "secret": None,
        "last_song": None,
        "waiting_room_policy": None,
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
        * `key` (`Optional[str]`) An optional key, if registration on the server is limited.
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


state: State = State()


@sio.on("update_config")
async def handle_update_config(data: dict[str, Any]) -> None:
    state.config = default_config() | data


@sio.on("skip-current")
async def handle_skip_current(data: dict[str, Any]) -> None:
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
    if state.current_source is not None:
        await state.current_source.skip_current(Entry(**data))


@sio.on("state")
async def handle_state(data: dict[str, Any]) -> None:
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
    state.queue = [Entry(**entry) for entry in data["queue"]]
    state.waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
    state.recent = [Entry(**entry) for entry in data["recent"]]

    for entry in state.queue[:2]:
        logger.info("Buffering: %s", entry.title)
        await sources[entry.source].buffer(entry)


@sio.on("connect")
async def handle_connect() -> None:
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
    logging.info("Connected to server")
    data = {
        "queue": state.queue,
        "waiting_room": state.waiting_room,
        "recent": state.recent,
        "config": state.config,
    }
    await sio.emit("register-client", data)


@sio.on("get-meta-info")
async def handle_get_meta_info(data: dict[str, Any]) -> None:
    """
    Handle a "get-meta-info" message.

    Collects the metadata for a given :py:class:`Entry`, from its source, and
    sends them back to the server in a "meta-info" message. On the server side
    a :py:func:`syng.server.handle_meta_info` function is called.

    :param data: A dictionary encoding the entry
    :type data: dict[str, Any]
    :rtype: None
    """
    source: Source = sources[data["source"]]
    meta_info: dict[str, Any] = await source.get_missing_metadata(Entry(**data))
    await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})


async def preview(entry: Entry) -> None:
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
            f"--image-display-duration={state.config['preview_duration']}",
            "--sub-pos=50",
            "--sub-file=-",
            "--fullscreen",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate(subtitle.encode())


@sio.on("play")
async def handle_play(data: dict[str, Any]) -> None:
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
        state.current_source = sources[entry.source]
        if state.config["preview_duration"] > 0:
            await preview(entry)
        await sources[entry.source].play(entry)
    except Exception:  # pylint: disable=broad-except
        print_exc()
    state.current_source = None
    if entry.skip:
        await sio.emit("get-first")
    else:
        await sio.emit("pop-then-get-next")


@sio.on("client-registered")
async def handle_client_registered(data: dict[str, Any]) -> None:
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
        logging.info("Registered")
        print(f"Join here: {state.config['server']}/{data['room']}")
        qr = QRCode(box_size=20, border=2)
        qr.add_data(f"{state.config['server']}/{data['room']}")
        qr.make()
        qr.print_ascii()
        state.config["room"] = data["room"]
        await sio.emit("sources", {"sources": list(sources.keys())})
        if state.current_source is None:  # A possible race condition can occur here
            await sio.emit("get-first")
    else:
        logging.warning("Registration failed")
        await sio.disconnect()


@sio.on("request-config")
async def handle_request_config(data: dict[str, Any]) -> None:
    """
    Handle the "request-config" message.

    Sends the specific server side configuration for a given
    :py:class:`syng.sources.source.Source`.

    A Source can decide, that the config will be split up in multiple Parts.
    If this is the case, multiple "config-chunk" messages will be send with a
    running enumerator. Otherwise a singe "config" message will be send.

    :param data: A dictionary with the entry `source` and a string, that
        corresponds to the name of a source.
    :type data: dict[str, Any]
    :rtype: None
    """
    if data["source"] in sources:
        config: dict[str, Any] | list[dict[str, Any]] = await sources[data["source"]].get_config()
        if isinstance(config, list):
            num_chunks: int = len(config)
            for current, chunk in enumerate(config):
                await sio.emit(
                    "config-chunk",
                    {
                        "source": data["source"],
                        "config": chunk,
                        "number": current + 1,
                        "total": num_chunks,
                    },
                )
        else:
            await sio.emit("config", {"source": data["source"], "config": config})


def signal_handler() -> None:
    engineio.async_client.async_signal_handler()
    if state.current_source is not None:
        if state.current_source.player is not None:
            state.current_source.player.kill()


async def start_client(config: dict[str, Any]) -> None:
    """
    Initialize the client and connect to the server.

    :param config: Config options for the client
    :type config: dict[str, Any]
    :rtype: None
    """

    sources.update(configure_sources(config["sources"]))

    if "config" in config:
        last_song = (
            datetime.datetime.fromisoformat(config["config"]["last_song"]).timestamp()
            if "last_song" in config["config"] and config["config"]["last_song"]
            else None
        )
        state.config |= config["config"] | {"last_song": last_song}

    if not ("secret" in state.config and state.config["secret"]):
        state.config["secret"] = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )
        print(f"Generated secret: {state.config['secret']}")

    if not ("key" in state.config and state.config["key"]):
        state.config["key"] = ""

    await sio.connect(state.config["server"])

    asyncio.get_event_loop().add_signal_handler(signal.SIGINT, signal_handler)
    asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        await sio.wait()
    except asyncio.CancelledError:
        pass
    finally:
        if state.current_source is not None:
            if state.current_source.player is not None:
                state.current_source.player.kill()


def create_async_and_start_client(config: dict[str, Any]) -> None:
    asyncio.run(start_client(config))


def main() -> None:
    """Entry point for the syng-client script."""
    parser: ArgumentParser = ArgumentParser()

    parser.add_argument("--room", "-r")
    parser.add_argument("--secret", "-s")
    parser.add_argument(
        "--config-file",
        "-C",
        default=f"{os.path.join(platformdirs.user_config_dir('syng'), 'config.yaml')}",
    )
    parser.add_argument("--key", "-k", default=None)
    parser.add_argument("--server", "-S")

    args = parser.parse_args()

    try:
        with open(args.config_file, encoding="utf8") as file:
            config = load(file, Loader=Loader)
    except FileNotFoundError:
        config = {}

    if "config" not in config:
        config["config"] = {}

    config["config"] |= {"key": args.key}
    if args.room:
        config["config"] |= {"room": args.room}
    if args.secret:
        config["config"] |= {"secret": args.secret}
    if args.server:
        config["config"] |= {"server": args.server}

    create_async_and_start_client(config)


if __name__ == "__main__":
    main()
