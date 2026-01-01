"""
Module for the Server.

The server listens for incoming connections from playback clients and web
clients via the socket.io protocol.

It manages multiple independent rooms, each with its own queue and configuration.
If configured, the server can be in private mode, where only playback clients with
a valid registration key can connect. It can also be in restricted mode, where only
search is forwarded to the playback client, unless the client has a valid registration
key.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import os
import random
import string
import uuid
from json.decoder import JSONDecodeError
from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from typing import Any, Callable, Literal, AsyncGenerator, Optional, cast

import socketio
from socketio.exceptions import ConnectionRefusedError
from aiohttp import web

try:
    from profanity_check import predict
except ImportError:
    # If the profanity_check package is not installed, use a dummy function
    def predict(strings: list[str]) -> list[Literal[0, 1]]:
        return [0]


from syng.sources.source import EntryNotValid

from .result import Result

from . import jsonencoder
from . import SYNG_VERSION, SYNG_PROTOCOL_VERSION
from .log import logger
from .entry import Entry
from .queue import Queue
from .sources import available_sources
from .sources import Source

DEFAULT_CONFIG = {
    "preview_duration": 3,
    "waiting_room_policy": None,
    "allow_collab_mode": True,
    "last_song": None,
}


def with_state(handler: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that forwards the state of a room to a handler.

    :param forward_room: Either the handler to decorate or a boolean
        defining if the room should be forwarded.
    :type forward_room: bool | Callable[..., Any]
    :return: The decorated handler or a function that decorates a handler
    :rtype: Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]
    """

    async def wrapper(self: Server, sid: str, *args: Any, **kwargs: Any) -> Any:
        async with self.sio.session(sid) as session:
            room = session["room"]
        state = self.clients[room]
        return await handler(self, state, sid, *args, **kwargs)

    return wrapper


def admin(handler: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator, that requires the client to be an admin.

    If the client is not an admin, the handler is not called.

    :param handler: The handler to decorate
    :type handler: Callable[..., Any]
    :return: The decorated handler
    :rtype: Callable[..., Any]
    """

    async def wrapper(self: Server, sid: str, *args: Any, **kwargs: Any) -> Any:
        async with self.sio.session(sid) as session:
            room = session["room"]
            if room not in self.clients or not await self.is_admin(self.clients[room], sid):
                await self.sio.emit("err", {"type": "NO_ADMIN"}, sid)
                return
        return await handler(self, sid, *args, **kwargs)

    return wrapper


def playback(handler: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator, that requires the client to be a playback client.

    If the client is not a playback client, the handler is not called.

    :param handler: The handler to decorate
    :type handler: Callable[..., Any]
    :return: The decorated handler
    :rtype: Callable[..., Any]
    """

    async def wrapper(self: Server, sid: str, *args: Any, **kwargs: Any) -> Any:
        async with self.sio.session(sid) as session:
            room = session["room"]
        state = self.clients[room]
        if sid != state.sid:
            return
        return await handler(self, sid, *args, **kwargs)

    return wrapper


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
        * `allow_collab_mode` (`bool`): True if users can tag their entries with
             collaboration requests.
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


class Server:
    def __init__(self) -> None:
        self.sio = socketio.AsyncServer(
            cors_allowed_origins="*", logger=True, engineio_logger=False, json=jsonencoder
        )
        self.app = web.Application()
        self.runner = web.AppRunner(self.app)
        self.admin_app = web.Application()
        self.admin_runner = web.AppRunner(self.admin_app)
        self.clients: dict[str, State] = {}
        self.sio.attach(self.app)
        self.register_handlers()

    def register_handlers(self) -> None:
        self.sio.on("get-state", self.handle_get_state)
        self.sio.on("waiting-room-append", self.handle_waiting_room_append)
        self.sio.on("show-config", self.handle_show_config)
        self.sio.on("update-config", self.handle_update_config)
        self.sio.on("append", self.handle_append)
        self.sio.on("append-anyway", self.handle_append_anyway)
        self.sio.on("meta-info", self.handle_meta_info)
        self.sio.on("get-first", self.handle_get_first)
        self.sio.on("waiting-room-to-queue", self.handle_waiting_room_to_queue)
        self.sio.on("queue-to-waiting-room", self.handle_queue_to_waiting_room)
        self.sio.on("pop-then-get-next", self.handle_pop_then_get_next)
        self.sio.on("sources", self.handle_sources)
        self.sio.on("config-chunk", self.handle_config_chunk)
        self.sio.on("config", self.handle_config)
        self.sio.on("register-admin", self.handle_register_admin)
        self.sio.on("remove-room", self.handle_remove_room)
        self.sio.on("skip-current", self.handle_skip_current)
        self.sio.on("move-to", self.handle_move_to)
        self.sio.on("move-up", self.handle_move_up)
        self.sio.on("skip", self.handle_skip)
        self.sio.on("disconnect", self.handle_disconnect)
        self.sio.on("connect", self.handle_connect)
        self.sio.on("search", self.handle_search)
        self.sio.on("search-results", self.handle_search_results)
        self.sio.on("import-queue", self.handle_import_queue)

    async def is_admin(self, state: State, sid: str) -> bool:
        """
        Check if a given sid is an admin in a room.

        :param room: The room to check
        :type room: str
        :param sid: The session id to check
        :type sid: str
        :return: True if the sid is an admin in the room, False otherwise
        :rtype: bool
        """
        if state.sid == sid:
            return True
        async with self.sio.session(sid) as session:
            return "admin" in session and session["admin"]

    async def root_handler(self, request: Any) -> Any:
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
            return web.FileResponse(os.path.join(self.app["root_folder"], "favicon.ico"))
        return web.FileResponse(os.path.join(self.app["root_folder"], "index.html"))

    def get_number_connections(self) -> int:
        """
        Get the number of connections to the server.

        :return: The number of connections
        :rtype: int
        """
        num = 0
        for namespace in self.sio.manager.get_namespaces():
            for room in self.sio.manager.rooms[namespace]:
                for participant in self.sio.manager.get_participants(namespace, room):
                    num += 1
        return num

    def get_connections(self) -> dict[str, dict[str, list[tuple[str, str]]]]:
        """
        Get all connections to the server.

        :return: A dictionary mapping namespaces to rooms and participants.
        :rtype: dict[str, dict[str, list[tuple[str, str]]]]
        """
        connections: dict[str, dict[str, list[tuple[str, str]]]] = {}
        for namespace in self.sio.manager.get_namespaces():
            connections[namespace] = {}
            for room in self.sio.manager.rooms[namespace]:
                connections[namespace][room] = []
                for participant in self.sio.manager.get_participants(namespace, room):
                    connections[namespace][room].append(participant)
        return connections

    async def get_clients(self, room: str) -> list[dict[str, Any]]:
        """
        Get the number of clients in a room.

        :param room: The room to get the number of clients for
        :type room: str
        :return: The number of clients in the room
        :rtype: int
        """
        clients = []
        for sid, client_id in self.sio.manager.get_participants("/", room):
            client: dict[str, Any] = {}
            client["sid"] = sid
            if sid == self.clients[room].sid:
                client["type"] = "playback"
            else:
                client["type"] = "web"
            client["admin"] = await self.is_admin(self.clients[room], sid)
            clients.append(client)
        return clients

    async def admin_handler(self, request: Any) -> Any:
        """
        Handle the admin request.
        """

        rooms = [
            {
                "room": room,
                "sid": state.sid,
                "last_seen": state.last_seen.isoformat(),
                "queue": state.queue.to_list(),
                "waiting_room": state.waiting_room,
                "clients": await self.get_clients(room),
            }
            for room, state in self.clients.items()
        ]
        info_dict = {
            "version": SYNG_VERSION,
            "protocol_version": SYNG_PROTOCOL_VERSION,
            "num_connections": self.get_number_connections(),
            "connections": self.get_connections(),
            "rooms": rooms,
        }
        return web.json_response(info_dict, dumps=jsonencoder.dumps)

    async def broadcast_state(
        self, state: State, /, sid: Optional[str] = None, room: Optional[str] = None
    ) -> None:
        if room is None:
            sid = state.sid if sid is None else sid
            async with self.sio.session(sid) as session:
                room = cast(str, session["room"])
        await self.send_state(state, room)

    async def log_to_playback(self, state: State, msg: str, level: str = "info") -> None:
        """
        Log a message to the playback client.

        This is used to inform the playback client of errors or other messages.

        :param state: The state of the room
        :type state: State
        :param msg: The message to send
        :type msg: str
        :rtype: None
        """
        await self.sio.emit("msg", {"msg": msg, "type": level}, room=state.sid)

    async def send_state(self, state: State, sid: str) -> None:
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

        await self.sio.emit(
            "state",
            {
                "queue": state.queue,
                "recent": state.recent,
                "waiting_room": state.waiting_room,
                "config": safe_config,
            },
            room=sid,
        )

    @with_state
    async def handle_get_state(self, state: State, sid: str) -> None:
        """
        Handle the "get-state" message.

        Sends the current state to whoever requests it. This failes if the sender
        is not part of any room.

        :param sid: The initial sender, and therefore recepient of the "state"
            message
        :type sid: str
        :rtype: None
        """
        await self.send_state(state, sid)

    @with_state
    async def handle_waiting_room_append(
        self, state: State, sid: str, data: dict[str, Any]
    ) -> Optional[str]:
        """
        Append a song to the waiting room.

        This should be called from a web client. Appends the entry, that is encoded
        within the data to the waiting room of the room the client is currently
        connected to.

        :param sid: The session id of the client sending this request
        :type sid: str
        :param data: A dictionary encoding the entry, that should be added to the
            waiting room.
        :type data: dict[str, Any]
        :return: The uuid of the added entry or None if the entry could not be added
        :rtype: Optional[str]
        """
        if not state.client.config["allow_collab_mode"]:
            data["collab_mode"] = None
        source_obj = state.client.sources[data["source"]]
        try:
            entry = await source_obj.get_entry(
                data["performer"],
                data["ident"],
                data.get("collab_mode", None),
                artist=data["artist"],
                title=data["title"],
            )
            if entry is None:
                await self.sio.emit(
                    "msg",
                    {
                        "msg": f"Unable to add to the waiting room: {data['ident']}. Maybe try again?"
                    },
                    room=sid,
                )
                return None
        except EntryNotValid as e:
            await self.sio.emit(
                "msg",
                {"msg": f"Unable to add to the waiting room: {data['ident']}. {e}"},
                room=sid,
            )
            return None

        if "uid" not in data or (
            (data["uid"] is not None and len(list(state.queue.find_by_uid(data["uid"]))) == 0)
            or (data["uid"] is None and state.queue.find_by_name(data["performer"]) is None)
        ):
            await self.append_to_queue(state, entry, sid)
            return None

        entry.uid = data["uid"]

        state.waiting_room.append(entry)
        await self.broadcast_state(state, sid=sid)
        await self.sio.emit(
            "get-meta-info",
            entry,
            room=state.sid,
        )
        return str(entry.uuid)

    async def append_to_queue(
        self, state: State, entry: Entry, report_to: Optional[str] = None
    ) -> None:
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
        first_song = state.queue.try_peek()
        if first_song is None or first_song.started_at is None:
            start_time = datetime.datetime.now().timestamp()
        else:
            start_time = first_song.started_at

        start_time = state.queue.fold(
            lambda item, time: time + item.duration + state.client.config["preview_duration"] + 1,
            start_time,
        )

        if (report_to is None or not await self.is_admin(state, report_to)) and state.client.config[
            "last_song"
        ]:
            if state.client.config["last_song"] < start_time:
                if report_to is not None:
                    await self.sio.emit(
                        "err",
                        {
                            "type": "QUEUE_FULL",
                            "end_time": state.client.config["last_song"],
                        },
                        room=report_to,
                    )
                return

        state.queue.append(entry)
        await self.broadcast_state(state, sid=report_to)

        await self.sio.emit(
            "get-meta-info",
            entry,
            room=state.sid,
        )

    @admin
    @with_state
    async def handle_show_config(self, state: State, sid: str) -> None:
        """
        Sends public config to webclient.

        This will only be send if the client is on an admin connection.

        :param sid: The session id of the client sending this request
        :type sid: str
        :rtype: None
        """
        await self.sio.emit(
            "config",
            state.client.config,
            sid,
        )

    @admin
    @with_state
    async def handle_update_config(self, state: State, sid: str, data: dict[str, Any]) -> None:
        """
        Forwards an updated config from an authorized webclient to the playback client.

        This is currently untrested and should be used with caution.

        :param sid: The session id of the client sending this request
        :type sid: str
        :param data: A dictionary encoding the new configuration
        :type data: dict[str, Any]
        :rtype: None
        """
        try:
            config = jsonencoder.loads(data["config"])
            await self.sio.emit(
                "update_config",
                DEFAULT_CONFIG | config,
                state.sid,
            )
            state.client.config = DEFAULT_CONFIG | config
        except JSONDecodeError:
            await self.sio.emit("err", {"type": "JSON_MALFORMED"}, room=sid)

    @with_state
    async def handle_append(self, state: State, sid: str, data: dict[str, Any]) -> Optional[str]:
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
        :return: The uuid of the added entry or None if the entry could not be added
        :rtype: Optional[str]
        """
        if len(data["performer"]) > 50:
            await self.sio.emit("err", {"type": "NAME_LENGTH", "name": data["performer"]}, room=sid)
            return None

        if predict([data["performer"]]) == [1]:
            await self.sio.emit("err", {"type": "PROFANITY", "name": data["performer"]}, room=sid)
            return None

        if state.client.config["waiting_room_policy"] and (
            state.client.config["waiting_room_policy"].lower() == "forced"
            or state.client.config["waiting_room_policy"].lower() == "optional"
        ):
            old_entry = state.queue.find_by_name(data["performer"])
            if old_entry is not None:
                await self.sio.emit(
                    "ask_for_waitingroom",
                    {
                        "current_entry": {
                            "source": data["source"],
                            "performer": data["performer"],
                            "ident": data["ident"],
                            "collab_mode": data.get("collab_mode", None),
                            "artist": data.get("artist", None),
                            "title": data.get("title", None),
                            "uid": data.get("uid", None),
                        },
                        "old_entry": {
                            "artist": old_entry.artist,
                            "title": old_entry.title,
                            "performer": old_entry.performer,
                        },
                    },
                    room=sid,
                )
                return None

        if not state.client.config["allow_collab_mode"]:
            data["collab_mode"] = None
        source_obj = state.client.sources[data["source"]]

        try:
            entry = await source_obj.get_entry(
                data["performer"],
                data["ident"],
                data.get("collab_mode", None),
                artist=data.get("artist", None),
                title=data.get("title", None),
            )
            if entry is None:
                await self.sio.emit(
                    "msg",
                    {"msg": f"Unable to append {data['ident']}. Maybe try again?"},
                    room=sid,
                )
                return None
        except EntryNotValid as e:
            await self.sio.emit(
                "msg",
                {"msg": f"Unable to append {data['ident']}. {e}"},
                room=sid,
            )
            return None

        logger.debug(f"Appending {entry} to queue in room {state.sid}")
        entry.uid = data["uid"] if "uid" in data else None

        await self.append_to_queue(state, entry, sid)
        return str(entry.uuid)

    @with_state
    async def handle_append_anyway(
        self, state: State, sid: str, data: dict[str, Any]
    ) -> Optional[str]:
        """
        Appends a song to the queue, even if the performer is already in queue.

        Works the same as handle_append, but without the check if the performer is already
        in queue.

        Only if the waiting_room_policy is not configured as forced.

        :return: The uuid of the added entry or None if the entry could not be added
        :rtype: Optional[str]
        """
        if len(data["performer"]) > 50:
            await self.sio.emit("err", {"type": "NAME_LENGTH", "name": data["performer"]}, room=sid)
            return None

        if predict([data["performer"]]) == [1]:
            await self.sio.emit("err", {"type": "PROFANITY", "name": data["performer"]}, room=sid)
            return None

        if state.client.config["waiting_room_policy"].lower() == "forced":
            await self.sio.emit(
                "err",
                {"type": "WAITING_ROOM_FORCED"},
                room=sid,
            )
            return None

        if not state.client.config["allow_collab_mode"]:
            data["collab_mode"] = None

        source_obj = state.client.sources[data["source"]]

        try:
            entry = await source_obj.get_entry(
                data["performer"],
                data["ident"],
                data.get("collab_mode", None),
                artist=data["artist"],
                title=data["title"],
            )

            if entry is None:
                await self.sio.emit(
                    "msg",
                    {"msg": f"Unable to append {data['ident']}. Maybe try again?"},
                    room=sid,
                )
                return None
        except EntryNotValid as e:
            await self.sio.emit(
                "msg",
                {"msg": f"Unable to append {data['ident']}. {e}"},
                room=sid,
            )
            return None

        entry.uid = data["uid"] if "uid" in data else None

        await self.append_to_queue(state, entry, sid)
        return str(entry.uuid)

    @playback
    @with_state
    async def handle_meta_info(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        state.queue.update(
            data["uuid"],
            lambda item: item.update(**data["meta"], incomplete_data=False),
        )

        entry = state.queue.find_by_uuid(data["uuid"])
        if entry is not None:
            source = entry.source
            source_obj = state.client.sources[source]
            if not source_obj.is_valid(entry):
                await self.log_to_playback(
                    state, f"Entry {entry.ident} is not valid.", level="error"
                )
                await state.queue.remove(entry)
        else:
            for entry in state.waiting_room:
                if entry.uuid == data["uuid"] or str(entry.uuid) == data["uuid"]:
                    entry.update(**data["meta"], incomplete_data=False)

        await self.broadcast_state(state, sid=sid)

    @playback
    @with_state
    async def handle_get_first(self, state: State, sid: str) -> None:
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
        current = await state.queue.peek()
        current.started_at = datetime.datetime.now().timestamp()

        await self.sio.emit("play", current, room=sid)

    @admin
    @with_state
    async def handle_queue_to_waiting_room(
        self, state: State, sid: str, data: dict[str, Any]
    ) -> None:
        """
        Handle the "queue-to-waiting" message.

        If on an admin-connection, removes a song from the queue and appends it to
        the waiting room. If the performer has only one entry in the queue, it is
        put back into the queue immediately.

        :param sid: The session id of the requesting client
        :type sid: str
        :rtype: None
        """

        entry = state.queue.find_by_uuid(data["uuid"])
        if entry is not None:
            performer_entries = list(state.queue.find_all_by_name(entry.performer))
            print(performer_entries)
            if len(performer_entries) == 1:
                return
            await state.queue.remove(entry)
            state.waiting_room.append(entry)
            await self.broadcast_state(state, sid=sid)

    @admin
    @with_state
    async def handle_waiting_room_to_queue(
        self, state: State, sid: str, data: dict[str, Any]
    ) -> None:
        """
        Handle the "waiting-room-to-queue" message.

        If on an admin-connection, removes a song from the waiting room and appends it to
        the queue.

        :param sid: The session id of the requesting client
        :type sid: str
        :rtype: None
        """
        entry = next(
            (wr_entry for wr_entry in state.waiting_room if str(wr_entry.uuid) == data["uuid"]),
            None,
        )
        if entry is not None:
            state.waiting_room.remove(entry)
            await self.append_to_queue(state, entry, sid)

    async def add_songs_from_waiting_room(self, state: State) -> None:
        """
        Add all songs from the waiting room, that should be added to the queue.

        A song should be added if none of its performers are already queued.

        This should be called every time a song leaves the queue.

        :param room: The room holding the queue.
        :type room: str
        :rtype: None
        """
        wrs_to_remove = []
        for wr_entry in state.waiting_room:
            if state.queue.find_by_name(wr_entry.performer) is None:
                await self.append_to_queue(state, wr_entry)
                wrs_to_remove.append(wr_entry)

        for wr_entry in wrs_to_remove:
            state.waiting_room.remove(wr_entry)

    async def discard_first(self, state: State) -> Entry:
        """
        Gets the first element of the queue, handling resulting triggers.

        This function is used to get the first element of the queue, and handle
        the resulting triggers. This includes adding songs from the waiting room,
        and updating the state of the room.

        :param room: The room to get the first element from.
        :type room: str
        :rtype: Entry
        """

        old_entry = await state.queue.popleft()

        await self.add_songs_from_waiting_room(state)

        state.recent.append(old_entry)
        state.last_seen = datetime.datetime.now()

        return old_entry

    @playback
    @with_state
    async def handle_pop_then_get_next(self, state: State, sid: str) -> None:
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
        await self.discard_first(state)
        await self.broadcast_state(state, sid=sid)

        current = await state.queue.peek()
        current.started_at = datetime.datetime.now().timestamp()
        await self.broadcast_state(state, sid=sid)

        await self.sio.emit("play", current, room=sid)

    def check_registration(self, key: str) -> bool:
        """
        Check if a given key is in the registration keyfile.

        This is used to authenticate a client, if the server is in private or
        restricted mode.

        :param key: The key to check
        :type key: str
        :return: True if the key is in the registration keyfile, False otherwise
        :rtype: bool
        """
        with open(self.app["registration-keyfile"], encoding="utf8") as f:
            raw_keys = f.readlines()
            keys = [key[:64] for key in raw_keys]

            return key in keys

    async def check_client_version(self, client_version: tuple[int, int, int], sid: str) -> bool:
        """
        Check if a given version is compatible with the server.

        :param version: The version to check
        :type version: tuple[int, int, int]
        :return: True if the version is compatible, False otherwise
        :rtype: bool
        """
        if client_version < SYNG_PROTOCOL_VERSION:
            await self.sio.emit(
                "msg",
                {"type": "error", "msg": "Client is incompatible and outdated. Please update."},
                room=sid,
            )
            await self.sio.emit(
                "client-registered",
                {"success": False, "room": None, "reason": "PROTOCOL_VERSION"},
                room=sid,
            )
            raise ConnectionRefusedError("Client is incompatible and outdated. Please update.")

        if client_version > SYNG_VERSION:
            await self.sio.emit(
                "msg",
                {"type": "error", "msg": "Server is outdated. Please update."},
                room=sid,
            )
            raise ConnectionRefusedError("Server is outdated. Please update.")

        if client_version < SYNG_VERSION:
            await self.sio.emit(
                "msg",
                {"type": "warning", "msg": "Client is compatible but outdated. Please update."},
                room=sid,
            )
        return True

    @admin
    @with_state
    async def handle_import_queue(self, state: State, sid: str, data: dict[str, Any]) -> None:
        """
        Handle the "import-queue" message.

        This will add entries to the queue and waiting room from the client.

        The data dictionary should have the following keys:
            - `queue`, a list of entries to import into the queue
            - `waiting_room`, a list of entries to import into the waiting room

        :param sid: The session id of the client sending this request
        :type sid: str
        :param data: A dictionary with the keys described above
        :type data: dict[str, Any]
        :rtype: None
        """

        queue_entries = [Entry(**entry) for entry in data.get("queue", [])]
        waiting_room_entries = [Entry(**entry) for entry in data.get("waiting_room", [])]
        recent_entries = [Entry(**entry) for entry in data.get("recent", [])]

        state.queue.extend(queue_entries)
        state.waiting_room.extend(waiting_room_entries)
        state.recent.extend(recent_entries)

        await self.broadcast_state(state, sid=sid)

    @admin
    @with_state
    async def handle_remove_room(self, state: State, sid: str, data: dict[str, Any]) -> None:
        """
        Handle the "remove-room" message.

        This will remove the room from the server, and delete all associated data.
        This is only available on an admin connection.

        :param sid: The session id of the client sending this request
        :type sid: str
        :rtype: None
        """
        async with self.sio.session(sid) as session:
            room = cast(str, session["room"])
        if room not in self.clients:
            await self.sio.emit(
                "msg",
                {"type": "error", "msg": f"Room {room} does not exist."},
                room=sid,
            )
            return

        await self.sio.emit("room-removed", {"room": room}, room=sid)
        for client, _ in self.sio.manager.get_participants("/", room):
            await self.sio.leave_room(client, room)
            await self.sio.disconnect(client)
        del self.clients[room]
        logger.info("Removed room %s", room)

    @playback
    @with_state
    async def handle_sources(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        unused_sources = state.client.sources.keys() - data["sources"]
        new_sources = data["sources"] - state.client.sources.keys()

        for source in unused_sources:
            del state.client.sources[source]

        state.client.sources_prio = data["sources"]

        for name in new_sources:
            await self.sio.emit("request-config", {"source": name}, room=sid)

    @playback
    @with_state
    async def handle_config_chunk(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        if data["source"] not in state.client.sources:
            state.client.sources[data["source"]] = available_sources[data["source"]](data["config"])
        else:
            state.client.sources[data["source"]].add_to_config(data["config"], data["number"])

    @playback
    @with_state
    async def handle_config(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        state.client.sources[data["source"]] = available_sources[data["source"]](data["config"])

    async def handle_connect(
        self, sid: str, environ: dict[str, Any], auth: None | dict[str, Any] = None
    ) -> None:
        """
        Handle the "connect" message.

        This is called, when a client connects to the server. It will register the
        client and send the initial state of the room to the client.

        :param sid: The session id of the requesting client.
        :type sid: str
        :param data: A dictionary with the keys described in
            :py:func:`handle_register_client`.
        :type data: dict[str, Any]
        :rtype: None
        """
        logger.debug("Client %s connected", sid)
        if auth is None or "type" not in auth:
            logger.warning(
                "Client %s connected without auth data, fall back to old registration", sid
            )
            return
            # raise ConnectionRefusedError("No authentication data provided. Please register first.")

        match auth["type"]:
            case "playback":
                await self.register_playback_client(sid, auth)
            case "web":
                await self.register_web_client(sid, auth)

    async def register_web_client(self, sid: str, auth: dict[str, Any]) -> None:
        if auth["room"] in self.clients:
            logger.info("Client %s registered for room %s", sid, auth["room"])
            async with self.sio.session(sid) as session:
                session["room"] = auth["room"]
                await self.sio.enter_room(sid, session["room"])
            state = self.clients[session["room"]]
            await self.send_state(state, sid)
            is_admin = False
            if "secret" in auth:
                is_admin = auth["secret"] == state.client.config["secret"]
                async with self.sio.session(sid) as session:
                    session["admin"] = is_admin
            await self.sio.emit("admin", is_admin, room=sid)
        else:
            logger.warning(
                "Client %s tried to register for non-existing room %s", sid, auth["room"]
            )
            raise ConnectionRefusedError(
                f"Room {auth['room']} does not exist. Please register first."
            )

    async def register_playback_client(self, sid: str, data: dict[str, Any]) -> None:
        """
        Register a new playback client and create a new room if necessary.

        The data dictionary should have the following keys:
            - `room` (Optional), the requested room
            - `config`, an dictionary of initial configurations
            - `queue`, a list of initial entries for the queue. The entries are
                        encoded as a dictionary.
            - `recent`, a list of initial entries for the recent list. The entries
                        are encoded as a dictionary.
            - `secret`, the secret of the room
            - `version`, the version of the client as a triple of integers
            - `key`, a registration key given out by the server administrator

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
        if "version" not in data:
            pass
            # TODO: Fallback to old registration method

            # await self.sio.emit(
            #     "client-registered",
            #     {"success": False, "room": None, "reason": "NO_VERSION"},
            #     room=sid,
            # )
            return

        client_version = tuple(data["version"])
        if not await self.check_client_version(client_version, sid):
            return

        def gen_id(length: int = 4) -> str:
            client_id = "".join([random.choice(string.ascii_letters) for _ in range(length)])
            if client_id in self.clients:
                client_id = gen_id(length + 1)
            return client_id

        if "key" in data["config"]:
            data["config"]["key"] = hashlib.sha256(data["config"]["key"].encode()).hexdigest()

        if self.app["type"] == "private" and (
            "key" not in data["config"] or not self.check_registration(data["config"]["key"])
        ):
            await self.sio.emit(
                "client-registered",
                {
                    "success": False,
                    "room": None,
                    "reason": "PRIVATE",
                },
                room=sid,
            )
            raise ConnectionRefusedError(
                "Private server, registration key not provided or invalid."
            )

        room: str = (
            data["config"]["room"]
            if "room" in data["config"] and data["config"]["room"]
            else gen_id()
        )
        async with self.sio.session(sid) as session:
            session["room"] = room

        if room in self.clients:
            old_state: State = self.clients[room]
            if data["config"]["secret"] == old_state.client.config["secret"]:
                logger.info("Got new playback client connection for %s", room)
                old_state.sid = sid
                old_state.client = Client(
                    sources=old_state.client.sources,
                    sources_prio=old_state.client.sources_prio,
                    config=DEFAULT_CONFIG | data["config"],
                )
                await self.sio.enter_room(sid, room)
                await self.send_state(self.clients[room], sid)
            else:
                logger.warning("Got wrong secret for %s", room)
                raise ConnectionRefusedError(f"Wrong secret for room {room}.")
        else:
            logger.info("Registerd new playback client %s", room)
            initial_entries = [Entry(**entry) for entry in data["queue"]]
            initial_waiting_room = [Entry(**entry) for entry in data["waiting_room"]]
            initial_recent = [Entry(**entry) for entry in data["recent"]]

            self.clients[room] = State(
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

            await self.sio.enter_room(sid, room)
            await self.send_state(self.clients[room], sid)

    @with_state
    async def handle_register_admin(self, state: State, sid: str, data: dict[str, Any]) -> bool:
        """
        THIS IS DEPRECATED, REGISTRATION IS NOW DONE VIA THE CONNECT EVENT.

        Handle a "register-admin" message.

        If the client provides the correct secret for its room, the connection is
        upgraded to an admin connection.

        :param sid: The session id of the client, requesting admin.
        :type sid: str:
        :param data: A dictionary with at least a "secret" entry.
        :type data: dict[str, Any]
        :return: True, if the secret is correct, False otherwise
        :rtype: bool
        """
        is_admin: bool = data["secret"] == state.client.config["secret"]
        async with self.sio.session(sid) as session:
            session["admin"] = is_admin
        return is_admin

    @admin
    @with_state
    async def handle_skip_current(self, state: State, sid: str) -> None:
        """
        Handle a "skip-current" message.

        If this comes from an admin connection, forward the "skip-current" message
        to the playback client. This will be handled by the
        :py:func:`syng.client.handle_skip_current` function.

        :param sid: The session id of the client, requesting.
        :type sid: str
        :rtype: None
        """
        old_entry = await self.discard_first(state)
        await self.sio.emit("skip-current", old_entry, room=state.sid)
        await self.broadcast_state(state, sid=sid)

    @admin
    @with_state
    async def handle_move_to(self, state: State, sid: str, data: dict[str, Any]) -> None:
        """
        Handle the "move-to" message.

        If on an admin connection, moves the entry specified in the data to the
        position specified in the data.

        :param sid: The session id of the client requesting.
        :type sid: str
        :param data: A dictionary with at least an "uuid" and a "target" entry
        :type data: dict[str, Any]
        :rtype: None
        """
        await state.queue.move_to(data["uuid"], data["target"])
        await self.broadcast_state(state, sid=sid)

    @admin
    @with_state
    async def handle_move_up(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        await state.queue.move_up(data["uuid"])
        await self.broadcast_state(state, sid=sid)

    @admin
    @with_state
    async def handle_skip(self, state: State, sid: str, data: dict[str, Any]) -> None:
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
        entry = state.queue.find_by_uuid(data["uuid"])
        if entry is not None:
            logger.info("Skipping %s", entry)

            await self.add_songs_from_waiting_room(state)

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
        await self.broadcast_state(state, sid=sid)

    async def handle_disconnect(self, sid: str) -> None:
        """
        Handle the "disconnect" message.

        This message is send automatically, when a client disconnets.

        Remove the client from its room.

        :param sid: The session id of the client disconnecting
        :type sid: str
        :rtype: None
        """
        async with self.sio.session(sid) as session:
            room = session.get("room")
        if room is not None:
            await self.sio.leave_room(sid, room)

    @with_state
    async def handle_search(self, state: State, sid: str, data: dict[str, Any]) -> str:
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
        :return: The search id
        :rtype: str
        """
        query = data["query"]
        search_id = uuid.uuid4()
        if (
            self.app["type"] != "restricted"
            or "key" in state.client.config
            and self.check_registration(state.client.config["key"])
        ):
            asyncio.create_task(self.search_and_emit(search_id, query, state, sid))
        else:
            await self.sio.emit(
                "search", {"query": query, "sid": sid, "search_id": search_id}, room=state.sid
            )
        return str(search_id)

    async def search_and_emit(
        self, search_id: uuid.UUID, query: str, state: State, sid: str
    ) -> None:
        """
        Search for a query on a source and emit the results.

        :param search_id: The search id
        :type search_id: uuid.UUID
        :param query: The query to search for
        :type query: str
        :param state: The state of the room
        :type state: State
        :param sid: The session id of the client
        :type sid: str
        :rtype: list[Result]
        """

        results_list = await asyncio.gather(
            *[state.client.sources[source].search(query) for source in state.client.sources_prio]
        )

        results = [
            search_result for source_result in results_list for search_result in source_result
        ]
        await self.send_search_results(sid, results, search_id)

    @playback
    async def handle_search_results(self, sid: str, data: dict[str, Any]) -> None:
        """
        Handle the "search-results" message.

        This message is send by the playback client, once it has received search
        results. The results are send to the web client.

        The data dictionary should have the following keys:
            - `sid`, the session id of the web client (str)
            - `results`, a list of search results (list[dict[str, Any]])
            - `search_id`, the search id (str) (Optional)

        :param sid: The session id of the playback client
        :type sid: str
        :param data: A dictionary with the keys described above
        :type data: dict[str, Any]
        :rtype: None
        """
        web_sid = data["sid"]
        search_id = data["search_id"] if "search_id" in data else None

        results = [Result.from_dict(result) for result in data["results"]]

        await self.send_search_results(web_sid, results, search_id)

    async def send_search_results(
        self, sid: str, results: list[Result], search_id: Optional[uuid.UUID]
    ) -> None:
        """
        Send search results to a client.

        :param sid: The session id of the client to send the results to.
        :type sid: str
        :param results: The search results to send.
        :type results: list[Result]
        :rtype: None
        """
        await self.sio.emit(
            "search-results",
            {"results": results, "search_id": search_id},
            room=sid,
        )

    async def cleanup(self) -> None:
        """
        Clean up the unused playback clients

        This runs every hour, and removes every client, that did not requested a song for four hours.

        :rtype: None
        """

        logger.info("Start Cleanup")
        to_remove: list[str] = []
        for sid, state in self.clients.items():
            logger.debug("Client %s, last seen: %s", sid, str(state.last_seen))
            if state.last_seen + datetime.timedelta(hours=4) < datetime.datetime.now():
                logger.info("No activity for 4 hours, removing %s", sid)
                to_remove.append(sid)
        for sid in to_remove:
            await self.sio.disconnect(sid)
            del self.clients[sid]

        # The internal loop counter does not use a regular timestamp, so we need to convert between
        # regular datetime and the async loop time
        now = datetime.datetime.now()

        next_run = now + datetime.timedelta(hours=1)
        offset = next_run.timestamp() - now.timestamp()
        loop_next = asyncio.get_event_loop().time() + offset

        logger.info("End cleanup, next cleanup at %s", str(next_run))
        asyncio.get_event_loop().call_at(loop_next, lambda: asyncio.create_task(self.cleanup()))

    async def background_tasks(
        self,
        iapp: web.Application,
    ) -> AsyncGenerator[None, None]:
        """
        Create all the background tasks.

        For now, this is only the cleanup task.

        :param iapp: The web application
        :type iapp: web.Application
        :rtype: AsyncGenerator[None, None]
        """

        iapp["repeated_cleanup"] = asyncio.create_task(self.cleanup())

        yield

        iapp["repeated_cleanup"].cancel()
        await iapp["repeated_cleanup"]

    async def run_apps(self, host: str, port: int, admin_port: Optional[int]) -> None:
        """
        Run the main and admin apps.

        This is used to run the main app and the admin app in parallel.

        :param host: The host to bind to
        :type host: str
        :param port: The port to bind to
        :type port: int
        :param admin_port: The port for the admin interface, or None if not used
        :type admin_port: Optional[int]
        :rtype: None
        """
        if admin_port:
            logger.info("Starting admin interface on port %d", admin_port)
            print(f"==== Admin Interface on {host}:{admin_port} ====")
            await self.admin_runner.setup()
            admin_site = web.TCPSite(self.admin_runner, host, admin_port)
            await admin_site.start()
        logger.info("Starting main server on port %d", port)
        print(f"==== Server on {host}:{port} ====")
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        await site.start()

        while True:
            await asyncio.sleep(3600)

    def run(self, args: Namespace) -> None:
        """
        Run the server.

        `args` consists of the following attributes:
            - `host`, the host to bind to
            - `port`, the port to bind to
            - `root_folder`, the root folder of the web client
            - `registration_keyfile`, the file containing the registration keys
            - `private`, if the server is private
            - `restricted`, if the server is restricted
            - `admin_port`, the port for the admin interface

        :param args: The command line arguments
        :type args: Namespace
        :rtype: None
        """
        self.app["type"] = (
            "private" if args.private else "restricted" if args.restricted else "public"
        )
        if args.registration_keyfile:
            self.app["registration-keyfile"] = args.registration_keyfile

        self.app["root_folder"] = args.root_folder

        self.app.add_routes(
            [web.static("/assets/", os.path.join(self.app["root_folder"], "assets/"))]
        )

        self.app.router.add_route("*", "/", self.root_handler)
        self.app.router.add_route("*", "/{room}", self.root_handler)
        self.app.router.add_route("*", "/{room}/", self.root_handler)
        self.admin_app.router.add_route("*", "/", self.admin_handler)

        self.app.cleanup_ctx.append(self.background_tasks)
        # if args.admin_password:
        #     self.sio.instrument(auth={"username": "admin", "password": args.admin_password})

        try:
            asyncio.run(
                self.run_apps(
                    args.host,
                    args.port,
                    args.admin_port,
                )
            )
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Shutting down server...")
            asyncio.run(self.runner.cleanup())
            asyncio.run(self.admin_runner.cleanup())
            logger.info("Server shut down.")


def run_server(args: Namespace) -> None:
    """
    Run the server.

    :param args: The command line arguments
    :type args: Namespace
    :rtype: None
    """
    loglevel = getattr(logging, args.log_level.upper(), logging.WARNING)
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger.setLevel(loglevel)
    server = Server()
    server.run(args)
