import asyncio
from typing import Any

from aiocmd import aiocmd
import socketio

from .result import Result
from .entry import Entry

sio: socketio.AsyncClient = socketio.AsyncClient()
state: dict[str, Any] = {}


@sio.on("search-results")
async def handle_search_results(data):
    for raw_item in data:
        item = Result(**raw_item)
        print(f"{item.artist} - {item.title} [{item.album}]")
        print(f"{item.source}: {item.id}")


@sio.on("state")
async def handle_state(data):
    print("New Queue")
    for raw_item in data["queue"]:
        item = Entry(**raw_item)
        print(f"\t{item.performer}:  {item.artist} - {item.title} ({item.duration})")
    print("Recent")
    for raw_item in data["recent"]:
        item = Entry(**raw_item)
        print(f"\t{item.performer}:  {item.artist} - {item.title} ({item.duration})")


@sio.on("connect")
async def handle_connect():
    print("Connected")
    await sio.emit("register-web", {"room": state["room"]})


@sio.on("register-admin")
async def handle_register_admin(data):
    if data["success"]:
        print("Logged in")
    else:
        print("Log in failed")


class SyngShell(aiocmd.PromptToolkitCmd):
    prompt = "syng> "

    def do_exit(self):
        return True

    async def do_stuff(self):
        await sio.emit(
            "append",
            {
                "performer": "Hammy",
                "source": "youtube",
                "id": "https://www.youtube.com/watch?v=rqZqHXJm-UA",  # https://youtube.com/watch?v=x5bM5Bdizi4",
            },
        )

    async def do_search(self, query):
        await sio.emit("search", {"query": query})

    async def do_append(self, source, ident):
        await sio.emit("append", {"performer": "Hammy", "source": source, "id": ident})

    async def do_admin(self, data):
        await sio.emit("register-admin", {"secret": data})

    async def do_connect(self, server, room):
        state["room"] = room
        await sio.connect(server)

    async def do_skip(self):
        await sio.emit("skip")

    async def do_queue(self):
        await sio.emit("get-state")


def main():
    asyncio.run(SyngShell().run())


if __name__ == "__main__":
    main()
