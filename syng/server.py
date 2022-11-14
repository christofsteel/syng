from __future__ import annotations
from collections import deque
from typing import Any
import asyncio
from dataclasses import dataclass

from aiohttp import web
import socketio

from .entry import Entry
from .sources import Source, available_sources

sio = socketio.AsyncServer(cors_allowed_origins="*", logger=True, engineio_logger=True)
app = web.Application()
sio.attach(app)


@dataclass
class State:
    admin_secret: str | None
    sources: dict[str, Source]
    sources_prio: list[str]


global_state = State(None, {}, [])


class Queue(deque):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num_of_entries_sem = asyncio.Semaphore(0)
        self.readlock = asyncio.Lock()

    async def append(self, item: Entry) -> None:
        super().append(item)
        await sio.emit("state", self.to_dict())
        self.num_of_entries_sem.release()

    async def peek(self) -> Entry:
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = super().popleft()
            super().appendleft(item)
            self.num_of_entries_sem.release()
        return item

    async def popleft(self) -> Entry:
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = super().popleft()
            await sio.emit("state", self.to_dict())
        return item

    def to_dict(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self]


queue = Queue()


@sio.on("get-state")
async def handle_state(sid, data: dict[str, Any] = {}):
    await sio.emit("state", queue.to_dict(), room=sid)


@sio.on("append")
async def handle_append(sid, data: dict[str, Any]):
    print(f"append: {data}")
    source_obj = global_state.sources[data["source"]]
    entry = await Entry.from_source(data["performer"], data["id"], source_obj)
    await queue.append(entry)
    print(f"new state: {queue.to_dict()}")

    await sio.emit(
        "buffer",
        entry.to_dict(),
        room="clients",
    )


@sio.on("meta-info")
async def handle_meta_info(sid, data):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            for item in queue:
                if str(item.uuid) == data["uuid"]:
                    item.update(**data["meta"])

            await sio.emit("state", queue.to_dict())


@sio.on("get-first")
async def handle_get_first(sid, data={}):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            current = await queue.peek()
            print(f"Sending {current} to client {sid}")
            await sio.emit("play", current.to_dict(), room=sid)


@sio.on("pop-then-get-next")
async def handle_pop_then_get_next(sid, data={}):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            await queue.popleft()
            current = await queue.peek()
            print(f"Sending {current} to client {sid}")
            await sio.emit("play", current.to_dict(), room=sid)


@sio.on("register-client")
async def handle_register_client(sid, data: dict[str, Any]):
    print(f"Registerd new client {sid}")
    global_state.admin_secret = data["secret"]
    await sio.save_session(sid, {"client": True})
    sio.enter_room(sid, "clients")
    await sio.emit("client-registered", {"success": True}, room=sid)


@sio.on("sources")
async def handle_sources(sid, data):
    """
    Get the list of sources the client wants to use.
    Update internal list of sources, remove unused
    sources and query for a config for all uninitialized sources
    """
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            unused_sources = global_state.sources.keys() - data["sources"]
            new_sources = data["sources"] - global_state.sources.keys()

            for source in unused_sources:
                del global_state.sources[source]

            global_state.sources_prio = data["sources"]

            for name in new_sources:
                await sio.emit("request-config", {"source": name}, room=sid)


@sio.on("config-chunk")
async def handle_config_chung(sid, data):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            if not data["source"] in global_state.sources:
                global_state.sources[data["source"]] = available_sources[
                    data["source"]
                ](data["config"])
            else:
                global_state.sources[data["source"]].add_to_config(data["config"])


@sio.on("config")
async def handle_config(sid, data):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            global_state.sources[data["source"]] = available_sources[data["source"]](
                data["config"]
            )
            print(f"Added source {data['source']}")


@sio.on("register-admin")
async def handle_register_admin(sid, data: dict[str, str]):
    if global_state.admin_secret and data["secret"] in global_state.admin_secret:
        print(f"Registerd new admin {sid}")
        await sio.save_session(sid, {"admin": True})
        await sio.emit("register-admin", {"success": True}, room=sid)
    else:
        await sio.emit("register-admin", {"success": False}, room=sid)


@sio.on("get-config")
async def handle_get_config(sid, data):
    async with sio.session(sid) as session:
        if "admin" in session and session["admin"]:
            await sio.emit(
                "config",
                {
                    name: source.get_config()
                    for name, source in global_state.sources.items()
                },
            )


@sio.on("skip")
async def handle_skip(sid, data={}):
    async with sio.session(sid) as session:
        if "admin" in session and session["admin"]:
            await sio.emit("skip", room="clients")


@sio.on("disconnect")
async def handle_disconnect(sid, data={}):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            sio.leave_room(sid, "clients")


@sio.on("search")
async def handle_search(sid, data: dict[str, str]):
    print(f"Got search request from {sid}: {data}")
    query = data["query"]
    result_futures = []
    for source in global_state.sources_prio:
        loop = asyncio.get_running_loop()
        search_future = loop.create_future()
        loop.create_task(global_state.sources[source].search(search_future, query))
        result_futures.append(search_future)

    results = [
        search_result
        for result_future in result_futures
        for search_result in await result_future
    ]
    print(f"Found {len(results)} results")
    await sio.emit("search-results", [result.to_dict() for result in results], room=sid)


def main() -> None:
    web.run_app(app, port=8080)


if __name__ == "__main__":
    main()
