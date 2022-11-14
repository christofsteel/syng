import asyncio
from traceback import print_exc
from json import load

import socketio

from .sources import Source, configure_sources
from .entry import Entry


sio = socketio.AsyncClient()

with open("./syng-client.json", encoding="utf8") as f:
    source_config = load(f)
sources: dict[str, Source] = configure_sources(source_config)

currentLock = asyncio.Semaphore(0)
state = {
    "current": None,
    "all_entries": {},
}


@sio.on("skip")
async def handle_skip():
    print("Skipping current")
    await state["current"].skip_current()


@sio.on("state")
async def handle_state(data):
    state["all_entries"] = {entry["uuid"]: Entry(**entry) for entry in data}


@sio.on("connect")
async def handle_connect():
    print("Connected to server")
    await sio.emit("register-client", {"secret": "test"})


@sio.on("buffer")
async def handle_buffer(data):
    source = sources[data["source"]]
    meta_info = await source.buffer(Entry(**data))
    await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})


@sio.on("play")
async def handle_play(data):
    entry = Entry(**data)
    print(f"Playing {entry}")
    try:
        meta_info = await sources[entry.source].buffer(entry)
        await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})
        state["current"] = sources[entry.source]
        await sources[entry.source].play(entry)
    except Exception:
        print_exc()
    await sio.emit("pop-then-get-next")


@sio.on("client-registered")
async def handle_register(data):
    if data["success"]:
        print("Registered")
        await sio.emit("sources", {"sources": list(source_config.keys())})
        await sio.emit("get-first")
    else:
        print("Registration failed")
        await sio.disconnect()


@sio.on("request-config")
async def handle_request_config(data):
    if data["source"] in sources:
        config = await sources[data["source"]].get_config()
        if isinstance(config, list):
            num_chunks = len(config)
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
            await sio.emit("config", {"source": data["source"], "config": config})


async def main():
    await sio.connect("http://127.0.0.1:8080")
    await sio.wait()


if __name__ == "__main__":
    asyncio.run(main())
