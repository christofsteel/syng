"""
Module for the playback client.

Excerp from the help::

    usage: client.py [-h] [--room ROOM] [--secret SECRET] \
            [--config-file CONFIG_FILE] server

    positional arguments:
      server

    options:
      -h, --help            show this help message and exit
      --room ROOM, -r ROOM
      --secret SECRET, -s SECRET
      --config-file CONFIG_FILE, -C CONFIG_FILE
      --key KEY, -k KEY

The config file should be a json file in the following style::

    {
      "sources": {
        "SOURCE1": { configuration for SOURCE },
        "SOURCE2": { configuration for SOURCE },
        ...
        },
      },
      "config": {
        configuration for the client
      }
    }
"""
import asyncio
import datetime
import logging
import secrets
import string
import tempfile
from argparse import ArgumentParser
from dataclasses import dataclass
from dataclasses import field
from json import load
from traceback import print_exc
from typing import Any
from typing import Optional

import pyqrcode
import socketio
from PIL import Image

from . import json
from .entry import Entry
from .sources import configure_sources
from .sources import Source


sio: socketio.AsyncClient = socketio.AsyncClient(json=json)
logger: logging.Logger = logging.getLogger(__name__)
sources: dict[str, Source] = {}


currentLock: asyncio.Semaphore = asyncio.Semaphore(0)


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
    :param room: The room on the server this playback client is connected to.
    :type room: str
    :param secret: The passcode of the room. If a playback client reconnects to
        a room, this must be identical. Also, if a webclient wants to have
        admin privileges, this must be included.
    :type secret: str
    :param key: An optional key, if registration on the server is limited.
    :type key: Optional[str]
    :param preview_duration: Amount of seconds the preview before a song be
        displayed.
    :type preview_duration: int
    :param last_song: At what time should the server not accept any more songs.
        `None` if no such limit should exist.
    :type last_song: Optional[datetime.datetime]
    """

    # pylint: disable=too-many-instance-attributes

    current_source: Optional[Source] = None
    queue: list[Entry] = field(default_factory=list)
    waiting_room: list[Entry] = field(default_factory=list)
    recent: list[Entry] = field(default_factory=list)
    room: str = ""
    server: str = ""
    secret: str = ""
    key: Optional[str] = None
    preview_duration: int = 3
    last_song: Optional[datetime.datetime] = None

    def get_config(self) -> dict[str, Any]:
        """
        Return a subset of values to be send to the server.

        Currently this is:
            - :py:attr:`State.preview_duration`
            - :py:attr:`State.last_song` (As a timestamp)

        :return: A dict resulting from the above values
        :rtype: dict[str, Any]
        """
        return {
            "preview_duration": self.preview_duration,
            "last_song": self.last_song.timestamp()
            if self.last_song
            else None,
        }


state: State = State()


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
        "room": state.room,
        "secret": state.secret,
        "config": state.get_config(),
    }
    if state.key:
        data["registration-key"] = state.key
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
    meta_info: dict[str, Any] = await source.get_missing_metadata(
        Entry(**data)
    )
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
            f"--image-display-duration={state.preview_duration}",
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
        if state.preview_duration > 0:
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
    Handle the "client-registered" massage.

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
        print(f"Join here: {state.server}/{data['room']}")
        print(
            pyqrcode.create(f"{state.server}/{data['room']}").terminal(
                quiet_zone=1
            )
        )
        state.room = data["room"]
        await sio.emit("sources", {"sources": list(sources.keys())})
        if (
            state.current_source is None
        ):  # A possible race condition can occur here
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
        config: dict[str, Any] | list[dict[str, Any]] = await sources[
            data["source"]
        ].get_config()
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
            await sio.emit(
                "config", {"source": data["source"], "config": config}
            )


async def aiomain() -> None:
    """
    Async main function.

    Parses the arguments, reads a config file and sets default values. Then
    connects to a specified server.

    If no secret is given, a random secret will be generated and presented to
    the user.

    :rtype: None
    """
    parser: ArgumentParser = ArgumentParser()

    parser.add_argument("--room", "-r")
    parser.add_argument("--secret", "-s")
    parser.add_argument("--config-file", "-C", default="syng-client.json")
    parser.add_argument("--key", "-k", default=None)
    parser.add_argument("server")

    args = parser.parse_args()

    with open(args.config_file, encoding="utf8") as file:
        config = load(file)
    sources.update(configure_sources(config["sources"]))

    if "config" in config:
        if "last_song" in config["config"]:
            state.last_song = datetime.datetime.fromisoformat(
                config["config"]["last_song"]
            )
        if "preview_duration" in config["config"]:
            state.preview_duration = config["config"]["preview_duration"]

    state.key = args.key if args.key else None

    if args.room:
        state.room = args.room

    if args.secret:
        state.secret = args.secret
    else:
        state.secret = "".join(
            secrets.choice(string.ascii_letters + string.digits)
            for _ in range(8)
        )
        print(f"Generated secret: {state.secret}")

    state.server = args.server

    await sio.connect(args.server)
    await sio.wait()


def main() -> None:
    """Entry point for the syng-client script."""
    asyncio.run(aiomain())


if __name__ == "__main__":
    main()
