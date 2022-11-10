from __future__ import annotations
from collections import deque
from typing import Any
import asyncio

# from flask import Flask
# from flask_socketio import SocketIO, emit  # type: ignore
from aiohttp import web
import socketio

from .entry import Entry
from .sources import configure_sources

# socketio = SocketIO(app, cors_allowed_origins='*')
# sio = socketio.AsyncServer()

sio = socketio.AsyncServer(cors_allowed_origins="*", logger=True, engineio_logger=True)
app = web.Application()
sio.attach(app)

admin_secrets = ["admin"]
client_secrets = ["test"]
sources = {}


class Queue(deque):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num_of_entries_sem = asyncio.Semaphore(0)
        self.readlock = asyncio.Lock()

    async def append(self, item: Entry) -> None:
        super().append(item)
        await sio.emit("state", self.to_dict())
        self.num_of_entries_sem.release()

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
async def handle_state(sid, data: dict[str, Any]):
    await sio.emit("state", queue.to_dict(), room=sid)


@sio.on("append")
async def handle_append(sid, data: dict[str, Any]):

    print(f"append: {data}")
    source_obj = sources[data["source"]]
    entry = await Entry.from_source(data["performer"], data["id"], source_obj)
    await queue.append(entry)
    print(f"new state: {queue.to_dict()}")


@sio.on("get-next")
async def handle_next(sid, data: dict[str, Any]):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            print(f"get-next request from client {sid}")
            current = await queue.popleft()
            print(f"Sending {current} to client {sid}")
            print(f"new state: {queue.to_dict()}")
            await sio.emit("next", current.to_dict(), room=sid)


@sio.on("register-client")
async def handle_register_client(sid, data: dict[str, Any]):
    if data["secret"] in client_secrets:
        print(f"Registerd new client {sid}")
        await sio.save_session(sid, {"client": True})
        sio.enter_room(sid, "clients")
        await sio.emit("client-registered", {"success": True}, room=sid)
    else:
        await sio.emit("client-registered", {"success": False}, room=sid)


@sio.on("config")
async def handle_config(sid, data):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            sources.update(configure_sources(data["sources"], client=False))
            print(f"Updated Config: {sources}")


@sio.on("register-admin")
async def handle_register_admin(sid, data: dict[str, str]):
    if data["secret"] in admin_secrets:
        print(f"Registerd new admin {sid}")
        await sio.save_session(sid, {"admin": True})
        await sio.emit("register-admin", {"success": True}, room=sid)
    else:
        await sio.emit("register-admin", {"success": False}, room=sid)


@sio.on("get-config")
async def handle_config(sid, data):
    async with sio.session(sid) as session:
        if "admin" in session and session["admin"]:
            await sio.emit("config", list(sources.keys()))


@sio.on("skip")
async def handle_skip(sid, data={}):
    async with sio.session(sid) as session:
        if "admin" in session and session["admin"]:
            await sio.emit("skip", room="client")


@sio.on("disconnect")
async def handle_disconnect(sid, data={}):
    async with sio.session(sid) as session:
        if "client" in session and session["client"]:
            sio.leave_room(sid, "clients")


@sio.on("search")
async def handle_search(sid, data: dict[str, str]):
    print(f"Got search request from {sid}: {data}")
    query = data["query"]
    results = []
    for source in sources.values():
        results += await source.search(query)
    print(f"Found {len(results)} results")
    await sio.emit("search-results", [result.to_dict() for result in results], room=sid)


def main() -> None:
    web.run_app(app, port=8080)


if __name__ == "__main__":
    main()
