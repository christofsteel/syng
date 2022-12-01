from __future__ import annotations

import asyncio
import datetime
import logging
import random
import string
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Optional
from uuid import UUID

import socketio
from aiohttp import web

from .entry import Entry
from .sources import available_sources
from .sources import Source

sio = socketio.AsyncServer(cors_allowed_origins="*",
                           logger=True, engineio_logger=False)
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


class Queue:
    """A async queue with synchronization.

    This queue keeps track of the amount of entries by using a semaphore.

    :param initial_entries: Initial list of entries to add to the queue
    :type initial_entries: list[Entry]
    """

    def __init__(self, initial_entries: list[Entry]):
        """
        Construct the queue. And initialize the internal lock and semaphore.

        :param initial_entries: Initial list of entries to add to the queue
        :type initial_entries: list[Entry]
        """
        self._queue = deque(initial_entries)

        self.num_of_entries_sem = asyncio.Semaphore(len(self._queue))
        self.readlock = asyncio.Lock()

    def append(self, entry: Entry) -> None:
        """
        Append an entry to the queue, increase the semaphore.

        :param entry: The entry to add
        :type entry: Entry
        :rtype: None
        """
        self._queue.append(entry)
        self.num_of_entries_sem.release()

    async def peek(self) -> Entry:
        """
        Return the first entry in the queue.

        If the queue is empty, wait until the queue has at least one entry.

        :returns: First entry of the queue
        :rtype: Entry
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue[0]
            self.num_of_entries_sem.release()
        return item

    async def popleft(self) -> Entry:
        """
        Remove the first entry in the queue and return it.

        Decreases the semaphore. If the queue is empty, wait until the queue
        has at least one entry.

        :returns: First entry of the queue
        :rtype: Entry
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue.popleft()
        return item

    def to_dict(self) -> list[dict[str, Any]]:
        """
        Forward the to_dict request to all entries and return it in a list.

        This is done, so that the entries can be converted to a JSON object,
        when sending it to the web or playback client.

        :returns: A list with dictionaries, that encode the enties in the
            queue.
        :rtype: list[dict[str, Any]]
        """
        return [item.to_dict() for item in self._queue]

    def update(self, uuid: UUID | str, updater: Callable[[Entry], None]) -> None:
        """
        Update entries in the queue, identified by their uuid.

        :param uuid: The uuid of the entry to update
        :type uuid: UUID | str
        :param updater: A function, that updates the entry
        :type updater: Callable[[Entry], None]
        :rtype: None
        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                updater(item)

    def find_by_uuid(self, uuid: UUID | str) -> Optional[Entry]:
        """
        Find an entry by its uuid and return it.

        :param uuid: The uuid to search for.
        :type uuid: UUID | str
        :returns: The entry with the uuid or `None` if no such entry exists
        :rtype: Optional[Entry]
        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                return item
        return None

    async def remove(self, entry: Entry) -> None:
        """
        Remove an entry, if it exists. Decrease the semaphore.

        :param entry: The entry to remove
        :type entry: Entry
        :rtype: None
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            self._queue.remove(entry)

    async def move_up(self, uuid: str) -> None:
        """
        Move an :py:class:`syng.entry.Entry` with the uuid up in the queue.

        If it is called on the first two elements, nothing will happen.

        :param uuid: The uuid of the entry.
        :type uuid: str
        :rtype: None
        """
        async with self.readlock:
            uuid_idx = 0
            for idx, item in enumerate(self._queue):
                if item.uuid == uuid or str(item.uuid) == uuid:
                    uuid_idx = idx

            if uuid_idx > 1:
                tmp = self._queue[uuid_idx]
                self._queue[uuid_idx] = self._queue[uuid_idx - 1]
                self._queue[uuid_idx - 1] = tmp


@dataclass
class Config:
    sources: dict[str, Source]
    sources_prio: list[str]
    preview_duration: int
    last_song: Optional[float]


@dataclass
class State:
    secret: str | None
    queue: Queue
    recent: list[Entry]
    sid: str
    config: Config


clients: dict[str, State] = {}


async def send_state(state: State, sid: str) -> None:
    await sio.emit(
        "state",
        {
            "queue": state.queue.to_dict(),
            "recent": [entry.to_dict() for entry in state.recent],
        },
        room=sid,
    )


@sio.on("get-state")
async def handle_state(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    await send_state(state, sid)


@sio.on("append")
async def handle_append(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    source_obj = state.config.sources[data["source"]]
    entry = await Entry.from_source(data["performer"], data["id"], source_obj)

    first_song = state.queue._queue[0] if len(state.queue._queue) > 0 else None
    if first_song is None or first_song.started_at is None:
        start_time = datetime.datetime.now().timestamp()
    else:
        start_time = first_song.started_at

    for item in state.queue._queue:
        start_time += item.duration + state.config.preview_duration + 1

    print(state.config.last_song)
    print(start_time)

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
        entry.to_dict(),
        room=clients[room].sid,
    )


@sio.on("meta-info")
async def handle_meta_info(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    state.queue.update(
        data["uuid"],
        lambda item: item.update(**data["meta"]),
    )

    await send_state(state, room)


@sio.on("get-first")
async def handle_get_first(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    current = await state.queue.peek()
    current.started_at = datetime.datetime.now().timestamp()

    await sio.emit("play", current.to_dict(), room=sid)


@sio.on("pop-then-get-next")
async def handle_pop_then_get_next(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    old_entry = await state.queue.popleft()
    state.recent.append(old_entry)

    await send_state(state, room)
    current = await state.queue.peek()
    current.started_at = datetime.datetime.now().timestamp()
    await send_state(state, room)

    await sio.emit("play", current.to_dict(), room=sid)


def gen_id(length: int = 4) -> str:
    client_id = "".join([random.choice(string.ascii_letters)
                        for _ in range(length)])
    if client_id in clients:
        client_id = gen_id(length + 1)
    return client_id


@sio.on("register-client")
async def handle_register_client(sid: str, data: dict[str, Any]) -> None:
    """
    [TODO:description]

    :param sid str: [TODO:description]
    :param data dict[str, Any]: [TODO:description]
    :rtype None: [TODO:description]
    """
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
    Get the list of sources the client wants to use.
    Update internal list of sources, remove unused
    sources and query for a config for all uninitialized sources
    """
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    unused_sources = state.config.sources.keys() - data["sources"]
    new_sources = data["sources"] - state.config.sources.keys()

    for source in unused_sources:
        del state.config.sources[source]

    state.config.sources_prio = data["sources"]

    for name in new_sources:
        await sio.emit("request-config", {"source": name}, room=sid)


@sio.on("config-chunk")
async def handle_config_chung(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if not data["source"] in state.config.sources:
        state.config.sources[data["source"]] = available_sources[data["source"]](
            data["config"]
        )
    else:
        state.config.sources[data["source"]].add_to_config(data["config"])


@sio.on("config")
async def handle_config(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    state.config.sources[data["source"]] = available_sources[data["source"]](
        data["config"]
    )


@sio.on("register-web")
async def handle_register_web(sid: str, data: dict[str, Any]) -> bool:
    if data["room"] in clients:
        async with sio.session(sid) as session:
            session["room"] = data["room"]
            sio.enter_room(sid, session["room"])
        state = clients[session["room"]]
        await send_state(state, sid)
        return True
    return False


@sio.on("register-admin")
async def handle_register_admin(sid: str, data: dict[str, str]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    is_admin = data["secret"] == state.secret
    async with sio.session(sid) as session:
        session["admin"] = is_admin
    await sio.emit("register-admin", {"success": is_admin}, room=sid)


@sio.on("get-config")
async def handle_get_config(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]

    if is_admin:
        await sio.emit(
            "config",
            {
                name: source.get_config()
                for name, source in state.config.sources.items()
            },
        )


@sio.on("skip-current")
async def handle_skip_current(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]

    if is_admin:
        await sio.emit("skip-current", room=clients[room].sid)


@sio.on("move-up")
async def handle_move_up(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]
    state = clients[room]
    if is_admin:
        await state.queue.move_up(data["uuid"])
        await send_state(state, room)


@sio.on("skip")
async def handle_skip(sid: str, data: dict[str, Any]) -> None:
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
async def handle_disconnect(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        sio.leave_room(sid, session["room"])


@sio.on("search")
async def handle_search(sid: str, data: dict[str, str]) -> None:
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
    # for source in state.config.sources_prio:
    #     loop = asyncio.get_running_loop()
    #     search_future = loop.create_future()
    #     loop.create_task(state.config.sources[source].search(search_future, query))
    #     result_futures.append(search_future)

    results = [
        search_result
        for source_result in results_list
        for search_result in source_result
    ]
    await sio.emit(
        "search-results",
        {"results": [result.to_dict() for result in results]},
        room=sid,
    )


def main() -> None:
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
