import asyncio
from typing import Any

from aiocmd import aiocmd
import socketio

from .result import Result
from .entry import Entry

sio: socketio.AsyncClient = socketio.AsyncClient()
state: dict[str, Any] = {}


@sio.on("search-results")
async def handle_search_results(data: dict[str, Any]) -> None:
    for raw_item in data["results"]:
        item = Result(**raw_item)
        print(f"{item.artist} - {item.title} [{item.album}]")
        print(f"{item.source}: {item.id}")


@sio.on("state")
async def handle_state(data: dict[str, Any]) -> None:
    print("New Queue")
    for raw_item in data["queue"]:
        item = Entry(**raw_item)
        print(f"\t{item.performer}:  {item.artist} - {item.title} ({item.duration})")
    print("Recent")
    for raw_item in data["recent"]:
        item = Entry(**raw_item)
        print(f"\t{item.performer}:  {item.artist} - {item.title} ({item.duration})")


@sio.on("connect")
async def handle_connect(_: dict[str, Any]) -> None:
    print("Connected")
    await sio.emit("register-web", {"room": state["room"]})


@sio.on("register-admin")
async def handle_register_admin(data: dict[str, Any]) -> None:
    if data["success"]:
        print("Logged in")
    else:
        print("Log in failed")


class SyngShell(aiocmd.PromptToolkitCmd):
    prompt = "syng> "

    def do_exit(self) -> bool:
        return True

    async def do_stuff(self) -> None:
        await sio.emit(
            "append",
            {
                "performer": "Hammy",
                "source": "youtube",
                "id": "https://www.youtube.com/watch?v=rqZqHXJm-UA",  # https://youtube.com/watch?v=x5bM5Bdizi4",
            },
        )

    async def do_search(self, query: str) -> None:
        await sio.emit("search", {"query": query})

    async def do_append(self, source: str, ident: str) -> None:
        await sio.emit("append", {"performer": "Hammy", "source": source, "id": ident})

    async def do_admin(self, data: str) -> None:
        await sio.emit("register-admin", {"secret": data})

    async def do_connect(self, server: str, room: str) -> None:
        state["room"] = room
        await sio.connect(server)

    async def do_skip(self) -> None:
        await sio.emit("skip")

    async def do_queue(self) -> None:
        await sio.emit("get-state")


def main() -> None:
    asyncio.run(SyngShell().run())


if __name__ == "__main__":
    main()
