"""
Module for the Server.

Starts a async socketio server, and serves the web client::

    usage: server.py [-h] [--host HOST] [--port PORT]

    options:
      -h, --help            show this help message and exit
      --host HOST, -H HOST
      --port PORT, -p PORT

"""
from __future__ import annotations

import asyncio
import datetime
import logging
import random
import string
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Any
from typing import Optional

import socketio
from aiohttp import web

from . import json
from .entry import Entry
from .queue import Queue
from .sources import available_sources
from .sources import Source

sio = socketio.AsyncServer(
    cors_allowed_origins="*", logger=True, engineio_logger=False, json=json
)
app = web.Application()
sio.attach(app)


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
        return web.FileResponse("syng/static/favicon.ico")
    return web.FileResponse("syng/static/index.html")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """This stores the configuration of a specific playback client.

    In case a new playback client connects to a room, these values can be
    overwritten.

    :param sources: A dictionary mapping the name of the used sources to their
        instances.
    :type sources: Source
    :param sources_prio: A list defining the order of the search results.
    :type sources_prio: list[str]
    :param preview_duration: The duration in seconds the playbackclients shows
        a preview for the next song. This is accounted for in the calculation
        of the ETA for songs later in the queue.
    :type preview_duration: int
    :param last_song: A timestamp, defining the end of the queue.
    :type last_song: Optional[float]
    """

    sources: dict[str, Source]
    sources_prio: list[str]
    preview_duration: int
    last_song: Optional[float]


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
    :param recent: A list of already played songs in order.
    :type recent: list[Entry]
    :param sid: The socket.io session id of the (unique) playback client. Once
        a new playback client connects to a room (with the correct secret),
        this will be swapped with the new sid.
    :type sid: str
    :param config: The config for the client
    :type config: Config
    """

    secret: str
    queue: Queue
    recent: list[Entry]
    sid: str
    config: Config


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
    await sio.emit(
        "state",
        {"queue": state.queue, "recent": state.recent},
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


@sio.on("append")
async def handle_append(sid: str, data: dict[str, Any]) -> None:
    """
    Handle the "append" message.

    This should be called from a web client. Appends the entry, that is encoded
    within the data to the room the client is currently connected to. An entry
    constructed this way, will be given a UUID, to differentiate it from other
    entries for the same song.

    If the room is configured to no longer accept songs past a certain time
    (via the :py:attr:`Config.last_song` attribute), it is checked, if the
    start time of the song would exceed this time. If this is the case, the
    request is denied and a "msg" message is send to the client, detailing
    this.

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

    source_obj = state.config.sources[data["source"]]
    entry = await source_obj.get_entry(data["performer"], data["ident"])

    first_song = state.queue.try_peek()
    if first_song is None or first_song.started_at is None:
        start_time = datetime.datetime.now().timestamp()
    else:
        start_time = first_song.started_at

    start_time = state.queue.fold(
        lambda item, time: time + item.duration + state.config.preview_duration + 1,
        start_time,
    )

    if state.config.last_song:
        if state.config.last_song < start_time:
            end_time = datetime.datetime.fromtimestamp(state.config.last_song)
            await sio.emit(
                "msg",
                {
                    "msg": f"The song queue ends at {end_time.hour:02d}:{end_time.minute:02d}."
                },
                room=sid,
            )
            return

    state.queue.append(entry)
    await send_state(state, room)

    await sio.emit(
        "get-meta-info",
        entry,
        room=clients[room].sid,
    )


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

    old_entry = await state.queue.popleft()
    state.recent.append(old_entry)

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
        client_id = "".join(
            [random.choice(string.ascii_letters) for _ in range(length)]
        )
        if client_id in clients:
            client_id = gen_id(length + 1)
        return client_id

    room: str = data["room"] if "room" in data and data["room"] else gen_id()
    async with sio.session(sid) as session:
        session["room"] = room

    print(data["config"])
    if room in clients:
        old_state: State = clients[room]
        if data["secret"] == old_state.secret:
            logger.info("Got new client connection for %s", room)
            old_state.sid = sid
            old_state.config = Config(
                sources=old_state.config.sources,
                sources_prio=old_state.config.sources_prio,
                **data["config"],
            )
            sio.enter_room(sid, room)
            await sio.emit(
                "client-registered", {"success": True, "room": room}, room=sid
            )
            await send_state(clients[room], sid)
        else:
            logger.warning("Got wrong secret for %s", room)
            await sio.emit(
                "client-registered", {"success": False, "room": room}, room=sid
            )
    else:
        logger.info("Registerd new client %s", room)
        initial_entries = [Entry(**entry) for entry in data["queue"]]
        initial_recent = [Entry(**entry) for entry in data["recent"]]

        clients[room] = State(
            secret=data["secret"],
            queue=Queue(initial_entries),
            recent=initial_recent,
            sid=sid,
            config=Config(sources={}, sources_prio=[], **data["config"]),
        )
        sio.enter_room(sid, room)
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

    unused_sources = state.config.sources.keys() - data["sources"]
    new_sources = data["sources"] - state.config.sources.keys()

    for source in unused_sources:
        del state.config.sources[source]

    state.config.sources_prio = data["sources"]

    for name in new_sources:
        await sio.emit("request-config", {"source": name}, room=sid)


@sio.on("config-chunk")
async def handle_config_chung(sid: str, data: dict[str, Any]) -> None:
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

    if not data["source"] in state.config.sources:
        state.config.sources[data["source"]] = available_sources[data["source"]](
            data["config"]
        )
    else:
        state.config.sources[data["source"]].add_to_config(data["config"])


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

    state.config.sources[data["source"]] = available_sources[data["source"]](
        data["config"]
    )


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
            sio.enter_room(sid, session["room"])
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

    is_admin: bool = data["secret"] == state.secret
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
        old_entry = await state.queue.popleft()
        state.recent.append(old_entry)
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
    from the queue.

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
            await state.queue.remove(entry)
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
            sio.leave_room(sid, session["room"])


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
        *[
            state.config.sources[source].search(query)
            for source in state.config.sources_prio
        ]
    )

    results = [
        search_result
        for source_result in results_list
        for search_result in source_result
    ]
    await sio.emit(
        "search-results",
        {"results": results},
        room=sid,
    )


def main() -> None:
    """
    Configure and start the server.

    Parse the command line arguments, register static routes to serve the web
    client and start the server.

    :rtype: None
    """
    parser = ArgumentParser()
    parser.add_argument("--host", "-H", default="localhost")
    parser.add_argument("--port", "-p", default="8080")
    args = parser.parse_args()

    app.add_routes([web.static("/assets/", "syng/static/assets/")])
    app.router.add_route("*", "/", root_handler)
    app.router.add_route("*", "/{room}", root_handler)
    app.router.add_route("*", "/{room}/", root_handler)

    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
