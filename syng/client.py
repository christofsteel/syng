import asyncio
import string
import secrets
from traceback import print_exc
from json import load
import logging
from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import Optional, Any
import tempfile
import datetime

import socketio
import pyqrcode
from PIL import Image

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
    preview_duration: int = 3
    last_song: Optional[datetime.datetime] = None

    def get_config(self) -> dict[str, Any]:
        return {
            "preview_duration": self.preview_duration,
            "last_song": self.last_song.timestamp() if self.last_song else None,
        }


state: State = State()


@sio.on("skip-current")
async def handle_skip_current(_: dict[str, Any] = {}) -> None:
    logger.info("Skipping current")
    if state.current_source is not None:
        await state.current_source.skip_current(state.queue[0])


@sio.on("state")
async def handle_state(data: dict[str, Any]) -> None:
    state.queue = [Entry(**entry) for entry in data["queue"]]
    state.recent = [Entry(**entry) for entry in data["recent"]]

    for entry in state.queue[:2]:
        logger.info("Buffering: %s", entry.title)
        await sources[entry.source].buffer(entry)


@sio.on("connect")
async def handle_connect(_: dict[str, Any] = {}) -> None:
    logging.info("Connected to server")
    await sio.emit(
        "register-client",
        {
            "queue": [entry.to_dict() for entry in state.queue],
            "recent": [entry.to_dict() for entry in state.recent],
            "room": state.room,
            "secret": state.secret,
            "config": state.get_config(),
        },
    )


@sio.on("buffer")
async def handle_buffer(data: dict[str, Any]) -> None:
    source: Source = sources[data["source"]]
    meta_info: dict[str, Any] = await source.get_missing_metadata(Entry(**data))
    await sio.emit("meta-info", {"uuid": data["uuid"], "meta": meta_info})


async def preview(entry: Entry) -> None:
    background = Image.new("RGB", (1280, 720))
    subtitle: str = f"""1
00:00:00,00 --> 00:05:00,00
{entry.artist} - {entry.title}
{entry.performer}"""
    with tempfile.NamedTemporaryFile() as tmpfile:
        background.save(tmpfile, "png")
        process = await asyncio.create_subprocess_exec(
            "mpv",
            tmpfile.name,
            "--image-display-duration=3",
            "--sub-pos=50",
            "--sub-file=-",
            "--fullscreen",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate(subtitle.encode())


@sio.on("play")
async def handle_play(data: dict[str, Any]) -> None:
    entry: Entry = Entry(**data)
    print(
        f"Playing: {entry.artist} - {entry.title} [{entry.album}] ({entry.source}) for {entry.performer}"
    )
    try:
        state.current_source = sources[entry.source]
        await preview(entry)
        await sources[entry.source].play(entry)
    except Exception:
        print_exc()
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
        config = load(file)
    sources.update(configure_sources(config["sources"]))

    if "config" in config:
        if "last_song" in config["config"]:
            state.last_song = datetime.datetime.fromisoformat(
                config["config"]["last_song"]
            )
        if "preview_duration" in config["config"]:
            state.preview_duration = config["config"]["preview_duration"]

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
