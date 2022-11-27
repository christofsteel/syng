import asyncio
import string
import secrets
from traceback import print_exc
from json import load
import logging
from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import Optional, Any

import socketio
import pyqrcode

from .sources import Source, configure_sources
from .entry import Entry


sio: socketio.AsyncClient = socketio.AsyncClient()
logger: logging.Logger = logging.getLogger(__name__)
sources: dict[str, Source] = {}


currentLock: asyncio.Semaphore = asyncio.Semaphore(0)


@dataclass
class State:
    current_source: Optional[Source] = None
    queue: list[Entry] = field(default_factory=list)
    recent: list[Entry] = field(default_factory=list)
    room: str = ""
    server: str = ""
    secret: str = ""


state: State = State()


@sio.on("skip")
async def handle_skip(_: dict[str, Any]) -> None:
    logger.info("Skipping current")
    if state.current_source is not None:
        await state.current_source.skip_current(state.queue[0])


@sio.on("state")
async def handle_state(data: dict[str, Any]) -> None:
    state.queue = [Entry(**entry) for entry in data["queue"]]
    state.recent = [Entry(**entry) for entry in data["recent"]]

    for entry in state.queue[:2]:
        logger.warning(f"Buffering: %s", entry.title)
        await sources[entry.source].buffer(entry)


@sio.on("connect")
async def handle_connect(_: dict[str, Any]) -> None:
    logging.info("Connected to server")
    await sio.emit(
        "register-client",
        {
            "secret": state.secret,
            "queue": [entry.to_dict() for entry in state.queue],
            "recent": [entry.to_dict() for entry in state.recent],
            "room": state.room,
        },
    )


@sio.on("buffer")
async def handle_buffer(data: dict[str, Any]) -> None:
    source: Source = sources[data["source"]]
    meta_info: dict[str, Any] = await source.get_missing_metadata(Entry(**data))
    await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})


@sio.on("play")
async def handle_play(data: dict[str, Any]) -> None:
    entry: Entry = Entry(**data)
    print(
        f"Playing: {entry.artist} - {entry.title} [{entry.album}] ({entry.source}) for {entry.performer}"
    )
    try:
        state.current_source = sources[entry.source]
        await sources[entry.source].play(entry)
    except Exception:
        print_exc()
    logging.info("Finished, waiting for next")
    await sio.emit("pop-then-get-next")


@sio.on("client-registered")
async def handle_register(data: dict[str, Any]) -> None:
    if data["success"]:
        logging.info("Registered")
        print(f"Join here: {state.server}/{data['room']}")
        print(pyqrcode.create(f"{state.server}/{data['room']}").terminal(quiet_zone=1))
        state.room = data["room"]
        await sio.emit("sources", {"sources": list(sources.keys())})
        if state.current_source is None:
            await sio.emit("get-first")
    else:
        logging.warning("Registration failed")
        await sio.disconnect()


@sio.on("request-config")
async def handle_request_config(data: dict[str, Any]) -> None:
    if data["source"] in sources:
        config: dict[str, Any] | list[dict[str, Any]] = await sources[
            data["source"]
        ].get_config()
        if isinstance(config, list):
            num_chunks: int = len(config)
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


async def aiomain() -> None:
    parser: ArgumentParser = ArgumentParser()

    parser.add_argument("--room", "-r")
    parser.add_argument("--secret", "-s")
    parser.add_argument("--config-file", "-C", default="syng-client.json")
    parser.add_argument("server")

    args = parser.parse_args()

    with open(args.config_file, encoding="utf8") as file:
        source_config = load(file)
    sources.update(configure_sources(source_config))
    if args.room:
        state.room = args.room

    if args.secret:
        state.secret = args.secret
    else:
        state.secret = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )
        print(f"Generated secret: {state.secret}")

    state.server = args.server

    await sio.connect(args.server)
    await sio.wait()


def main() -> None:
    asyncio.run(aiomain())


if __name__ == "__main__":
    main()
