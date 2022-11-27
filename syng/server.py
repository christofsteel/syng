from __future__ import annotations
from collections import deque
from typing import Any, Callable
import asyncio
from dataclasses import dataclass
import string
import random
import logging
from argparse import ArgumentParser


from aiohttp import web
import socketio

from .entry import Entry
from .sources import Source, available_sources

sio = socketio.AsyncServer(cors_allowed_origins="*", logger=True, engineio_logger=False)
app = web.Application()
sio.attach(app)


async def root_handler(request: Any) -> Any:
    return web.FileResponse("syng/static/index.html")


app.add_routes([web.static("/assets/", "syng/static/assets/")])
app.router.add_route("*", "/", root_handler)
app.router.add_route("*", "/{room}", root_handler)
app.router.add_route("*", "/{room}/", root_handler)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Queue:
    def __init__(self, initial_entries: list[Entry]):
        self._queue = deque(initial_entries)

        self.num_of_entries_sem = asyncio.Semaphore(len(self._queue))
        self.readlock = asyncio.Lock()

    def append(self, x: Entry) -> None:
        self._queue.append(x)
        self.num_of_entries_sem.release()

    async def peek(self) -> Entry:
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue[0]
            self.num_of_entries_sem.release()
        return item

    async def popleft(self) -> Entry:
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue.popleft()
        return item

    def to_dict(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._queue]

    def update(
        self, locator: Callable[[Entry], Any], updater: Callable[[Entry], None]
    ) -> None:
        for item in self._queue:
            if locator(item):
                updater(item)


@dataclass
class State:
    secret: str | None
    sources: dict[str, Source]
    sources_prio: list[str]
    queue: Queue
    recent: list[Entry]
    sid: str


clients: dict[str, State] = {}


@sio.on("get-state")
async def handle_state(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    await sio.emit(
        "state",
        {
            "queue": state.queue.to_dict(),
            "recent": [entry.to_dict() for entry in state.recent],
        },
        room=sid,
    )


@sio.on("append")
async def handle_append(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    source_obj = state.sources[data["source"]]
    entry = await Entry.from_source(data["performer"], data["id"], source_obj)
    state.queue.append(entry)
    await sio.emit(
        "state",
        {
            "queue": state.queue.to_dict(),
            "recent": [entry.to_dict() for entry in state.recent],
        },
        room=room,
    )

    await sio.emit(
        "buffer",
        entry.to_dict(),
        room=clients[room].sid,
    )


@sio.on("meta-info")
async def handle_meta_info(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    state.queue.update(
        lambda item: str(item.uuid) == data["uuid"],
        lambda item: item.update(**data["meta"]),
    )

    await sio.emit(
        "state",
        {
            "queue": state.queue.to_dict(),
            "recent": [entry.to_dict() for entry in state.recent],
        },
        room=room,
    )


@sio.on("get-first")
async def handle_get_first(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    current = await state.queue.peek()

    await sio.emit("play", current.to_dict(), room=sid)


@sio.on("pop-then-get-next")
async def handle_pop_then_get_next(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    old_entry = await state.queue.popleft()
    state.recent.append(old_entry)
    await sio.emit(
        "state",
        {
            "queue": state.queue.to_dict(),
            "recent": [entry.to_dict() for entry in state.recent],
        },
        room=room,
    )
    current = await state.queue.peek()

    await sio.emit("play", current.to_dict(), room=sid)


def gen_id(length: int = 4) -> str:
    client_id = "".join([random.choice(string.ascii_letters) for _ in range(length)])
    if client_id in clients:
        client_id = gen_id(length + 1)
    return client_id


@sio.on("register-client")
async def handle_register_client(sid: str, data: dict[str, Any]) -> None:
    room: str = data["room"] if "room" in data and data["room"] else gen_id()
    async with sio.session(sid) as session:
        session["room"] = room

    if room in clients:
        old_state: State = clients[room]
        if data["secret"] == old_state.secret:
            logger.info("Got new client connection for %s", room)
            old_state.sid = sid
            sio.enter_room(sid, room)
            await sio.emit(
                "client-registered", {"success": True, "room": room}, room=sid
            )
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
            data["secret"], {}, [], Queue(initial_entries), initial_recent, sid
        )
        sio.enter_room(sid, room)
        await sio.emit(
            "state",
            {
                "queue": clients[room].queue.to_dict(),
                "recent": [entry.to_dict() for entry in clients[room].recent],
            },
            room=sid,
        )
        await sio.emit("client-registered", {"success": True, "room": room}, room=sid)


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

    unused_sources = state.sources.keys() - data["sources"]
    new_sources = data["sources"] - state.sources.keys()

    for source in unused_sources:
        del state.sources[source]

    state.sources_prio = data["sources"]

    for name in new_sources:
        await sio.emit("request-config", {"source": name}, room=sid)


@sio.on("config-chunk")
async def handle_config_chung(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    if not data["source"] in state.sources:
        logger.info("Added source %s", data["source"])
        state.sources[data["source"]] = available_sources[data["source"]](
            data["config"]
        )
    else:
        state.sources[data["source"]].add_to_config(data["config"])


@sio.on("config")
async def handle_config(sid: str, data: dict[str, Any]) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
    state = clients[room]

    state.sources[data["source"]] = available_sources[data["source"]](data["config"])
    logger.info("Added source %s", data["source"])


@sio.on("register-web")
async def handle_register_web(sid: str, data: dict[str, Any]) -> bool:
    if data["room"] in clients:
        async with sio.session(sid) as session:
            session["room"] = data["room"]
            sio.enter_room(sid, session["room"])
        state = clients[session["room"]]
        await sio.emit(
            "state",
            {
                "queue": state.queue.to_dict(),
                "recent": [entry.to_dict() for entry in state.recent],
            },
            room=sid,
        )
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
            {name: source.get_config() for name, source in state.sources.items()},
        )


@sio.on("skip")
async def handle_skip(sid: str, data: dict[str, Any] = {}) -> None:
    async with sio.session(sid) as session:
        room = session["room"]
        is_admin = session["admin"]

    if is_admin:
        await sio.emit("skip", room=clients[room].sid)


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
    result_futures = []
    for source in state.sources_prio:
        loop = asyncio.get_running_loop()
        search_future = loop.create_future()
        loop.create_task(state.sources[source].search(search_future, query))
        result_futures.append(search_future)

    results = [
        search_result
        for result_future in result_futures
        for search_result in await result_future
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
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
