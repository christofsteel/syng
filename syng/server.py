"""
Module for the Server.

Starts a async socketio server, and serves the web client::

    usage: server.py [-h] [--host HOST] [--port PORT] [--root-folder PATH]

    options:
      -h, --help            show this help message and exit
      --host HOST, -H HOST
      --port PORT, -p PORT
      --root-folder PATH, -r PATH

"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import os
import random
import string
from json.decoder import JSONDecodeError
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from dataclasses import field
from sys import argv, stderr
from typing import Any
from typing import AsyncGenerator
from typing import Optional

import socketio
from aiohttp import web
from profanity_check import predict

from . import jsonencoder
from .entry import Entry
from .queue import Queue
from .sources import available_sources
from .sources import Source

sio = socketio.AsyncServer(
    cors_allowed_origins="*", logger=True, engineio_logger=False, json=jsonencoder
)
app = web.Application()
sio.attach(app)

DEFAULT_CONFIG = {
    "preview_duration": 3,
    "waiting_room_policy": None,
    "last_song": None,
}


async def root_handler(request: Any) -> Any:
    """
    Handle the index and favicon requests.

    If the path of the request ends with "/favicon.ico" return the favicon,
    otherwise the index.html. This way the javascript can read the room code
    from the url.

    :param request Any: Webrequest from aiohttp
    :return: Either the favicon or the index.html
    :rtype web.FileResponse:
    """
    if request.path.endswith("/favicon.ico"):
        return web.FileResponse(os.path.join(app["root_folder"], "favicon.ico"))
    return web.FileResponse(os.path.join(app["root_folder"], "index.html"))


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class Client:
    """This stores the configuration of a specific playback client.

    In case a new playback client connects to a room, these values can be
    overwritten.

    :param sources: A dictionary mapping the name of the used sources to their
        instances.
    :type sources: Source
    :param sources_prio: A list defining the order of the search results.
    :type sources_prio: list[str]
    :param config: Various configuration options for the client:
        * `preview_duration` (`Optional[int]`): The duration in seconds the
            playback client shows a preview for the next song. This is accounted for
            in the calculation of the ETA for songs later in the queue.
        * `last_song` (`Optional[float]`): A timestamp, defining the end of the queue.
        * `waiting_room_policy` (Optional[str]): One of:
            - `forced`, if a performer is already in the queue, they are put in the
                       waiting room.
            - `optional`, if a performer is already in the queue, they have the option
                          to be put in the waiting room.
            - `None`, performers are always added to the queue.
    :type config: dict[str, Any]:
    """

    sources: dict[str, Source]
    sources_prio: list[str]
    config: dict[str, Any]


@dataclass
class State:
    """This defines the state of one session/room.

    :param secret: The secret for the room. Used to log in as an admin on the
        webclient or reconnect a playbackclient
    :type secret: str
    :param queue: A queue of :py:class:`syng.entry.Entry` objects. New songs
        are appended to this, and if a playback client requests a song, it is
        taken from the top.
    :type queue: Queue
    :param waiting_room: Contains the Entries, that are hold back, until a
        specific song is finished.
    :type waiting_room: list[Entry]
    :param recent: A list of already played songs in order.
    :type recent: list[Entry]
    :param sid: The socket.io session id of the (unique) playback client. Once
        a new playback client connects to a room (with the correct secret),
        this will be swapped with the new sid.
    :type sid: str
    :param client: The config for the playback client
    :type client: Client
    :param last_seen: Timestamp of the last connected client. Used to determine
        if a room is still in use.
    :type last_seen: datetime
    """

    queue: Queue
    waiting_room: list[Entry]
    recent: list[Entry]
    sid: str
    client: Client
    last_seen: datetime.datetime = field(init=False, default_factory=datetime.datetime.now)


clients: dict[str, State] = {}


async def send_state(state: State, sid: str) -> None:
    """
    Send the current state (queue and recent-list) to sid.

    This sends a "state" message. This can be received either by the playback
    client, a web client or the whole room.

    If it is send to a playback client, it will be handled by the
    :py:func:`syng.client.handle_state` function.

    :param state: The state to send
    :type state: State
    :param sid: The recepient of the "state" message
    :type sid: str:
    :rtype: None
    """

    safe_config = {k: v for k, v in state.client.config.items() if k not in ["secret", "key"]}

    await sio.emit(
        "state",
        {
            "queue": state.queue,
            "recent": state.recent,
            "waiting_room": state.waiting_room,
            "config": safe_config,
        },
        room=sid,
    )


@sio.on("get-state")
async def handle_state(sid: str) -> None:
    """
    Handle the "get-state" message.

    Sends the current state to whoever requests it. This failes if the sender
    is not part of any room.

    :param sid: The initial sender, and therefore recepient of the "state"
        message
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    await send_state(state, sid)


@sio.on("waiting-room-append")
async def handle_waiting_room_append(sid: str, data: dict[str, Any]) -> None:
    """
    Append a song to the waiting room.

    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    source_obj = state.client.sources[data["source"]]

    entry = await source_obj.get_entry(data["performer"], data["ident"])

    if entry is None:
        await sio.emit(
            "msg",
            {"msg": f"Unable to add to the waiting room: {data['ident']}. Maybe try again?"},
            room=sid,
        )
        return

    if "uid" not in data or (
        (data["uid"] is not None and len(list(state.queue.find_by_uid(data["uid"]))) == 0)
        or (data["uid"] is None and state.queue.find_by_name(data["performer"]) is None)
    ):
        await append_to_queue(room, entry, sid)
        return

    entry.uid = data["uid"]

    state.waiting_room.append(entry)
    await send_state(state, room)
    await sio.emit(
        "get-meta-info",
        entry,
        room=clients[room].sid,
    )


async def append_to_queue(room: str, entry: Entry, report_to: Optional[str] = None) -> None:
    """
    Append a song to the queue for a given session.

    Checks, if the computed start time is before the configured end time of the
    event, and reports an error, if the end time is exceeded.

    :param room: The room with the queue.
    :type room: str
    :param entry: The entry that contains the song.
    :type entry: Entry
    :param report_to: If an error occurs, who to report to.
    :type report_to: Optional[str]
    :rtype: None
    """
    state = clients[room]

    first_song = state.queue.try_peek()
    if first_song is None or first_song.started_at is None:
        start_time = datetime.datetime.now().timestamp()
    else:
        start_time = first_song.started_at

    start_time = state.queue.fold(
        lambda item, time: time + item.duration + state.client.config["preview_duration"] + 1,
        start_time,
    )

    if state.client.config["last_song"]:
        if state.client.config["last_song"] < start_time:
            # end_time = datetime.datetime.fromtimestamp(
            #     state.client.config["last_song"]
            # )
            if report_to is not None:
                await sio.emit(
                    "err",
                    {
                        "type": "QUEUE_FULL",
                        "end_time": state.client.config["last_song"],
                    },
                    room=report_to,
                )
            return

    state.queue.append(entry)
    await send_state(state, room)

    await sio.emit(
        "get-meta-info",
        entry,
        room=clients[room].sid,
    )


@sio.on("show_config")
async def handle_show_config(sid: str) -> None:
    """
    Sends public config to webclient.

    This will only be send if the client is on an admin connection.

    :param sid: The session id of the client sending this request
    :type sid: str
    :rtype: None
    """

    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        await sio.emit(
            "config",
            state.client.config,
            sid,
        )
    else:
        await sio.emit("err", {"type": "NO_ADMIN"}, sid)


@sio.on("update_config")
async def handle_update_config(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        try:
            config = jsonencoder.loads(data["config"])
            await sio.emit(
                "update_config",
                DEFAULT_CONFIG | config,
                state.sid,
            )
            state.client.config = DEFAULT_CONFIG | config
            await sio.emit("update_config", config, room)
        except JSONDecodeError:
            await sio.emit("err", {"type": "JSON_MALFORMED"})

    else:
        await sio.emit("err", {"type": "NO_ADMIN"}, sid)


@sio.on("append")
async def handle_append(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "append" message.

    This should be called from a web client. Appends the entry, that is encoded
    within the data to the room the client is currently connected to. An entry
    constructed this way, will be given a UUID, to differentiate it from other
    entries for the same song. Additionally an id of the web client is saved
    for that entry.

    If the room is configured to no longer accept songs past a certain time
    (via the :py:attr:`Config.last_song` attribute), it is checked, if the
    start time of the song would exceed this time. If this is the case, the
    request is denied and a "msg" message is send to the client, detailing
    this.

    If a waitingroom is forced or optional, it is checked, if one of the performers is
    already in queue. In that case, a "ask_for_waitingroom" message is send to the
    client.

    Otherwise the song is added to the queue. And all connected clients (web
    and playback client) are informed of the new state with a "state" message.

    Since some properties of a song can only be accessed on the playback
    client, a "get-meta-info" message is send to the playback client. This is
    handled there with the :py:func:`syng.client.handle_get_meta_info`
    function.

    :param sid: The session id of the client sending this request
    :type sid: str
    :param data: A dictionary encoding the entry, that should be added to the
        queue.
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if len(data["performer"]) > 50:
        await sio.emit("err", {"type": "NAME_LENGTH", "name": data["performer"]}, room=sid)
        return

    if predict([data["performer"]]) == [1]:
        await sio.emit("err", {"type": "PROFANITY", "name": data["performer"]}, room=sid)
        return

    if state.client.config["waiting_room_policy"] and (
        state.client.config["waiting_room_policy"].lower() == "forced"
        or state.client.config["waiting_room_policy"].lower() == "optional"
    ):
        old_entry = state.queue.find_by_name(data["performer"])
        if old_entry is not None:
            await sio.emit(
                "ask_for_waitingroom",
                {
                    "current_entry": {
                        "source": data["source"],
                        "performer": data["performer"],
                        "ident": data["ident"],
                    },
                    "old_entry": {
                        "artist": old_entry.artist,
                        "title": old_entry.title,
                        "performer": old_entry.performer,
                    },
                },
                room=sid,
            )
            return

    source_obj = state.client.sources[data["source"]]

    entry = await source_obj.get_entry(data["performer"], data["ident"])

    if entry is None:
        await sio.emit(
            "msg",
            {"msg": f"Unable to append {data['ident']}. Maybe try again?"},
            room=sid,
        )
        return

    entry.uid = data["uid"] if "uid" in data else None

    await append_to_queue(room, entry, sid)


@sio.on("append-anyway")
async def handle_append_anyway(sid: str, data: dict[str, Any]) -> None:
    """
    Appends a song to the queue, even if the performer is already in queue.

    Works the same as handle_append, but without the check if the performer is already
    in queue.

    Only if the waiting_room_policy is not configured as forced.
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if len(data["performer"]) > 50:
        await sio.emit("err", {"type": "NAME_LENGTH", "name": data["performer"]}, room=sid)
        return

    if predict([data["performer"]]) == [1]:
        await sio.emit("err", {"type": "PROFANITY", "name": data["performer"]}, room=sid)
        return

    if state.client.config["waiting_room_policy"].lower() == "forced":
        await sio.emit(
            "err",
            {"type": "WAITING_ROOM_FORCED"},
            room=sid,
        )
        return

    source_obj = state.client.sources[data["source"]]

    entry = await source_obj.get_entry(data["performer"], data["ident"])

    if entry is None:
        await sio.emit(
            "msg",
            {"msg": f"Unable to append {data['ident']}. Maybe try again?"},
            room=sid,
        )
        return

    entry.uid = data["uid"] if "uid" in data else None

    print(entry)

    await append_to_queue(room, entry, sid)


@sio.on("meta-info")
async def handle_meta_info(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "meta-info" message.

    Updated a :py:class:syng.entry.Entry`, that is encoded in the data
    parameter, in the queue, that belongs to the room the requesting client
    belongs to, with new meta data, that is send from the playback client.

    Afterwards send the updated queue to all members of the room.

    :param sid: The session id of the client sending this request.
    :type sid: str
    :param data: A dictionary encoding the entry to update (already with the
        new metadata)
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    state.queue.update(
        data["uuid"],
        lambda item: item.update(**data["meta"]),
    )

    for entry in state.waiting_room:
        if entry.uuid == data["uuid"] or str(entry.uuid) == data["uuid"]:
            entry.update(**data["meta"])

    await send_state(state, room)


@sio.on("get-first")
async def handle_get_first(sid: str) -> None:
    """
    Handle the "get-first" message.

    This message is send by the playback client, once it has connected. It
    should only be send for the initial song. Each subsequent song should be
    requestet with a "pop-then-get-next" message (See
    :py:func:`handle_pop_then_get_next`).

    If no songs are in the queue for this room, this function waits until one
    is available, then notes its starting time and sends it back to the
    playback client in a "play" message. This will be handled by the
    :py:func:`syng.client.handle_play` function.

    :param sid: The session id of the requesting client
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    current = await state.queue.peek()
    current.started_at = datetime.datetime.now().timestamp()

    await sio.emit("play", current, room=sid)


@sio.on("waiting-room-to-queue")
async def handle_waiting_room_to_queue(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "waiting-room-to-queue" message.

    If on an admin-connection, removes a song from the waiting room and appends it to
    the queue.

    :param sid: The session id of the requesting client
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        entry = next(
            (wr_entry for wr_entry in state.waiting_room if str(wr_entry.uuid) == data["uuid"]),
            None,
        )
        if entry is not None:
            state.waiting_room.remove(entry)
            await append_to_queue(room, entry, sid)


async def add_songs_from_waiting_room(room: str) -> None:
    """
    Add all songs from the waiting room, that should be added to the queue.

    A song should be added if none of its performers are already queued.

    This should be called every time a song leaves the queue.

    :param room: The room holding the queue.
    :type room: str
    :rtype: None
    """
    state = clients[room]

    wrs_to_remove = []
    for wr_entry in state.waiting_room:
        if state.queue.find_by_name(wr_entry.performer) is None:
            await append_to_queue(room, wr_entry)
            wrs_to_remove.append(wr_entry)

    for wr_entry in wrs_to_remove:
        state.waiting_room.remove(wr_entry)


async def discard_first(room: str) -> Entry:
    """
    Gets the first element of the queue, handling resulting triggers.
    """
    state = clients[room]

    old_entry = await state.queue.popleft()

    await add_songs_from_waiting_room(room)

    state.recent.append(old_entry)
    state.last_seen = datetime.datetime.now()

    return old_entry


@sio.on("pop-then-get-next")
async def handle_pop_then_get_next(sid: str) -> None:
    """
    Handle the "pop-then-get-next" message.

    This function acts similar to the :py:func:`handle_get_first` function. The
    main difference is, that prior to sending a song to the playback client,
    the first element of the queue is discarded.

    Afterwards it follows the same steps as the handler for the "play" message,
    get the first element of the queue, annotate it with the current time,
    update everyones state and send the entry it to the playback client in a
    "play" message. This will be handled by the
    :py:func:`syng.client.handle_play` function.

    :param sid: The session id of the requesting playback client
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if sid != state.sid:
        return

    await discard_first(room)
    await send_state(state, room)

    current = await state.queue.peek()
    current.started_at = datetime.datetime.now().timestamp()
    await send_state(state, room)

    await sio.emit("play", current, room=sid)


@sio.on("register-client")
async def handle_register_client(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "register-client" message.

    The data dictionary should have the following keys:
        - `registration_key` (Optional), a key corresponding to those stored
                    in `app["registration-keyfile"]`
        - `room` (Optional), the requested room
        - `config`, an dictionary of initial configurations
        - `queue`, a list of initial entries for the queue. The entries are
                    encoded as a dictionary.
        - `recent`, a list of initial entries for the recent list. The entries
                    are encoded as a dictionary.
        - `secret`, the secret of the room

    This will register a new playback client to a specific room. If there
    already exists a playback client registered for this room, this
    playback client will be replaced if and only if, the new playback
    client has the same secret.

    If registration is restricted, abort, if the given key is not in the
    registration keyfile.

    If no room is provided, a fresh room id is generated.

    If the client provides a new room, or a new room id was generated, the
    server will create a new :py:class:`State` object and associate it with
    the room id. The state will be initialized with a queue and recent
    list, an initial config as well as no sources (yet).

    In any case, the client will be notified of the success or failure, along
    with its assigned room key via a "client-registered" message. This will be
    handled by the :py:func:`syng.client.handle_client_registered` function.

    If it was successfully registerd, the client will be added to its assigend
    or requested room.

    Afterwards all clients in the room will be send the current state.

    :param sid: The session id of the requesting playback client.
    :type sid: str
    :param data: A dictionary with the keys described above
    :type data: dict[str, Any]
    :rtype: None
    """

    def gen_id(length: int = 4) -> str:
        client_id = "".join([random.choice(string.ascii_letters) for _ in range(length)])
        if client_id in clients:
            client_id = gen_id(length + 1)
        return client_id

    if not app["public"]:
        with open(app["registration-keyfile"], encoding="utf8") as f:
            raw_keys = f.readlines()
            keys = [key[:64] for key in raw_keys]

            if (
                "key" not in data["config"]
                or hashlib.sha256(data["config"]["key"].encode()).hexdigest() not in keys
            ):
                await sio.emit(
                    "client-registered",
                    {"success": False, "room": None},
                    room=sid,
                )
                return

    room: str = (
        data["config"]["room"] if "room" in data["config"] and data["config"]["room"] else gen_id()
    )
    async with sio.session(sid) as session:
        session["room"] = room

    if room in clients:
        old_state: State = clients[room]
        if data["config"]["secret"] == old_state.client.config["secret"]:
            logger.info("Got new client connection for %s", room)
            old_state.sid = sid
            old_state.client = Client(
                sources=old_state.client.sources,
                sources_prio=old_state.client.sources_prio,
                config=DEFAULT_CONFIG | data["config"],
            )
            await sio.enter_room(sid, room)
            await sio.emit("client-registered", {"success": True, "room": room}, room=sid)
            await send_state(clients[room], sid)
        else:
            logger.warning("Got wrong secret for %s", room)
            await sio.emit("client-registered", {"success": False, "room": room}, room=sid)
    else:
        logger.info("Registerd new client %s", room)
        initial_entries = [Entry(**entry) for entry in data["queue"]]
        initial_waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
        initial_recent = [Entry(**entry) for entry in data["recent"]]

        clients[room] = State(
            queue=Queue(initial_entries),
            waiting_room=initial_waiting_room,
            recent=initial_recent,
            sid=sid,
            client=Client(
                sources={},
                sources_prio=[],
                config=DEFAULT_CONFIG | data["config"],
            ),
        )

        await sio.enter_room(sid, room)
        await sio.emit("client-registered", {"success": True, "room": room}, room=sid)
        await send_state(clients[room], sid)


@sio.on("sources")
async def handle_sources(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "sources" message.

    Get the list of sources the client wants to use. Update internal list of
    sources, remove unused sources and query for a config for all uninitialized
    sources by sending a "request-config" message for each such source to the
    playback client. This will be handled by the
    :py:func:`syng.client.request-config` function.

    This will not yet add the sources to the configuration, rather gather what
    sources need to be configured and request their configuration. The list
    of sources will set the :py:attr:`Config.sources_prio` attribute.

    :param sid: The session id of the playback client
    :type sid: str
    :param data: A dictionary containing a "sources" key, with the list of
        sources to use.
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if sid != state.sid:
        return

    unused_sources = state.client.sources.keys() - data["sources"]
    new_sources = data["sources"] - state.client.sources.keys()

    for source in unused_sources:
        del state.client.sources[source]

    state.client.sources_prio = data["sources"]

    for name in new_sources:
        await sio.emit("request-config", {"source": name}, room=sid)


@sio.on("config-chunk")
async def handle_config_chunk(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "config-chunk" message.

    This is called, when a source wants its configuration transmitted in
    chunks, rather than a single message. If the source already exist
    (e.g. when this is not the first chunk), the config will be added
    to the source, otherwise a source will be created with the given
    configuration.

    :param sid: The session id of the playback client
    :type sid: str
    :param data: A dictionary with a "source" (str) and a
        "config" (dict[str, Any]) entry. The exact content of the config entry
        depends on the source.
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if sid != state.sid:
        return

    if data["source"] not in state.client.sources:
        state.client.sources[data["source"]] = available_sources[data["source"]](data["config"])
    else:
        state.client.sources[data["source"]].add_to_config(data["config"])


@sio.on("config")
async def handle_config(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "config" message.

    This is called, when a source wants its configuration transmitted in
    a single message, rather than chunks. A source will be created with the
    given configuration.

    :param sid: The session id of the playback client
    :type sid: str
    :param data: A dictionary with a "source" (str) and a
        "config" (dict[str, Any]) entry. The exact content of the config entry
        depends on the source.
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if sid != state.sid:
        return

    state.client.sources[data["source"]] = available_sources[data["source"]](data["config"])


@sio.on("register-web")
async def handle_register_web(sid: str, data: dict[str, Any]) -> bool:
    """
    Handle a "register-web" message.

    Adds a web client to a requested room and sends it the initial state of the
    queue and recent list.

    :param sid: The session id of the web client.
    :type sid: str
    :param data: A dictionary, containing at least a "room" entry.
    :type data: dict[str, Any]
    :returns: True, if the room exist, False otherwise
    :rtype: bool
    """
    if data["room"] in clients:
        async with sio.session(sid) as session:
            session["room"] = data["room"]
            await sio.enter_room(sid, session["room"])
        state = clients[session["room"]]
        await send_state(state, sid)
        return True
    return False


@sio.on("register-admin")
async def handle_register_admin(sid: str, data: dict[str, Any]) -> bool:
    """
    Handle a "register-admin" message.

    If the client provides the correct secret for its room, the connection is
    upgraded to an admin connection.

    :param sid: The session id of the client, requesting admin.
    :type sid: str:
    :param data: A dictionary with at least a "secret" entry.
    :type data: dict[str, Any]
    :returns: True, if the secret is correct, False otherwise
    :rtype: bool
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    is_admin: bool = data["secret"] == state.client.config["secret"]
    async with sio.session(sid) as session:
        session["admin"] = is_admin
    return is_admin


@sio.on("skip-current")
async def handle_skip_current(sid: str) -> None:
    """
    Handle a "skip-current" message.

    If this comes from an admin connection, forward the "skip-current" message
    to the playback client. This will be handled by the
    :py:func:`syng.client.handle_skip_current` function.

    :param sid: The session id of the client, requesting.
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        old_entry = await discard_first(room)
        await sio.emit("skip-current", old_entry, room=clients[room].sid)
        await send_state(state, room)


@sio.on("move-up")
async def handle_move_up(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "move-up" message.

    If on an admin connection, moves up the entry specified in the data by one
    place in the queue.

    :param sid: The session id of the client requesting.
    :type sid: str
    :param data: A dictionary with at least an "uuid" entry
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]
    if is_admin:
        await state.queue.move_up(data["uuid"])
        await send_state(state, room)


@sio.on("skip")
async def handle_skip(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "skip" message.

    If on an admin connection, removes the entry specified by data["uuid"]
    from the queue or the waiting room. Triggers the waiting room.

    :param sid: The session id of the client requesting.
    :type sid: str
    :param data: A dictionary with at least an "uuid" entry.
    :type data: dict[str, Any]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        entry = state.queue.find_by_uuid(data["uuid"])
        if entry is not None:
            logger.info("Skipping %s", entry)

            await add_songs_from_waiting_room(room)

            await state.queue.remove(entry)

        first_entry_index = None
        for idx, wr_entry in enumerate(state.waiting_room):
            if wr_entry.uuid == data["uuid"]:
                first_entry_index = idx
                break

        if first_entry_index is not None:
            logger.info(
                "Deleting %s from waiting room",
                state.waiting_room[first_entry_index],
            )
            del state.waiting_room[first_entry_index]
        await send_state(state, room)


@sio.on("disconnect")
async def handle_disconnect(sid: str) -> None:
    """
    Handle the "disconnect" message.

    This message is send automatically, when a client disconnets.

    Remove the client from its room.

    :param sid: The session id of the client disconnecting
    :type sid: str
    :rtype: None
    """
    async with sio.session(sid) as session:
        if "room" in session:
            await sio.leave_room(sid, session["room"])


@sio.on("search")
async def handle_search(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "search" message.

    Forwards the dict["query"] to the :py:func:`Source.search` method, and
    execute them concurrently. The order is given by the
    :py:attr:`Config.sources_prio` attribute of the state.

    The result will be send with a "search-results" message to the (web)
    client.

    :param sid: The session id of the client requesting.
    :type sid: str
    :param data: A dictionary with at least a "query" entry.
    :type data: dict[str, str]
    :rtype: None
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    query = data["query"]
    results_list = await asyncio.gather(
        *[state.client.sources[source].search(query) for source in state.client.sources_prio]
    )

    results = [search_result for source_result in results_list for search_result in source_result]
    await sio.emit(
        "search-results",
        {"results": results},
        room=sid,
    )


async def cleanup() -> None:
    """Clean up the unused playback clients

    This runs every hour, and removes every client, that did not requested a song for four hours
    """

    logger.info("Start Cleanup")
    to_remove: list[str] = []
    for sid, state in clients.items():
        logger.info("Client %s, last seen: %s", sid, str(state.last_seen))
        if state.last_seen + datetime.timedelta(hours=4) < datetime.datetime.now():
            logger.info("No activity for 4 hours, removing %s", sid)
            to_remove.append(sid)
    for sid in to_remove:
        await sio.disconnect(sid)
        del clients[sid]
    logger.info("End Cleanup")

    # The internal loop counter does not use a regular timestamp, so we need to convert between
    # regular datetime and the async loop time
    now = datetime.datetime.now()
    # today = datetime.datetime(now.year, now.month, now.day)
    # next_run = today + datetime.timedelta(days=1)

    next_run = now + datetime.timedelta(hours=1)
    offset = next_run.timestamp() - now.timestamp()
    loop_next = asyncio.get_event_loop().time() + offset

    logger.info("Next Cleanup at %s", str(next))
    asyncio.get_event_loop().call_at(loop_next, lambda: asyncio.create_task(cleanup()))


async def background_tasks(
    iapp: web.Application,
) -> AsyncGenerator[None, None]:
    """Create all the background tasks

    For now, this is only the cleanup task
    """

    iapp["repeated_cleanup"] = asyncio.create_task(cleanup())

    yield

    iapp["repeated_cleanup"].cancel()
    await iapp["repeated_cleanup"]


def run_server(args: Namespace) -> None:
    app["public"] = True
    if args.registration_keyfile:
        app["public"] = False
        app["registration-keyfile"] = args.registration_keyfile

    app["root_folder"] = args.root_folder

    app.add_routes([web.static("/assets/", os.path.join(app["root_folder"], "assets/"))])

    app.router.add_route("*", "/", root_handler)
    app.router.add_route("*", "/{room}", root_handler)
    app.router.add_route("*", "/{room}/", root_handler)

    app.cleanup_ctx.append(background_tasks)

    web.run_app(app, host=args.host, port=args.port)


def main() -> None:
    """
    Configure and start the server.

    Parse the command line arguments, register static routes to serve the web
    client and start the server.

    :rtype: None
    """

    print(
        f"Starting the server with {argv[0]} is deprecated. Please use `syng server` to start the server",
        file=stderr,
    )

    root_path = os.path.join(os.path.dirname(__file__), "static")
    parser = ArgumentParser()
    parser.add_argument("--host", "-H", default="localhost")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument("--root-folder", "-r", default=root_path)
    parser.add_argument("--registration-keyfile", "-k", default=None)
    args = parser.parse_args()

    run_server(args)


if __name__ == "__main__":
    main()
