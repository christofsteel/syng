from __future__ import annotations
import shlex
import asyncio
from typing import Tuple, Optional, Type, Any
import os.path
from collections import defaultdict
from dataclasses import dataclass, field

from ..entry import Entry
from ..result import Result


@dataclass
class DLFilesEntry:
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    video: str = ""
    audio: Optional[str] = None
    buffering: bool = False
    complete: bool = False
    skip: bool = False


class Source:
    def __init__(self, config: dict[str, Any]):
        self.downloaded_files: defaultdict[str, DLFilesEntry] = defaultdict(
            DLFilesEntry
        )
        self.masterlock: asyncio.Lock = asyncio.Lock()
        self.player: Optional[asyncio.subprocess.Process] = None
        self.extra_mpv_arguments: list[str] = []

    @staticmethod
    async def play_mpv(
        video: str, audio: str | None, /, *options: str
    ) -> asyncio.subprocess.Process:
        args = ["--fullscreen", *options, video] + (
            [f"--audio-file={audio}"] if audio else []
        )

        mpv_process = asyncio.create_subprocess_exec("mpv", *args)
        return await mpv_process

    async def get_entry(self, performer: str, ident: str) -> Entry:
        raise NotImplementedError

    async def search(
        self, result_future: asyncio.Future[list[Result]], query: str
    ) -> None:
        raise NotImplementedError

    async def doBuffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        raise NotImplementedError

    async def buffer(self, entry: Entry) -> None:
        async with self.masterlock:
            if self.downloaded_files[entry.id].buffering:
                print(f"already buffering {entry.title}")
                return
            self.downloaded_files[entry.id].buffering = True

        video, audio = await self.doBuffer(entry)
        self.downloaded_files[entry.id].video = video
        self.downloaded_files[entry.id].audio = audio
        self.downloaded_files[entry.id].complete = True
        self.downloaded_files[entry.id].ready.set()
        print(f"Buffering done for {entry.title}")

    async def play(self, entry: Entry) -> None:
        await self.ensure_playable(entry)
        self.player = await self.play_mpv(
            self.downloaded_files[entry.id].video,
            self.downloaded_files[entry.id].audio,
            *self.extra_mpv_arguments,
        )
        await self.player.wait()

    async def skip_current(self, entry: Entry) -> None:
        if self.player is not None:
            self.player.kill()

    async def ensure_playable(self, entry: Entry) -> None:
        await self.buffer(entry)
        await self.downloaded_files[entry.id].ready.wait()

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        return {}

    def filter_data_by_query(self, query: str, data: list[str]) -> list[str]:
        def contains_all_words(words: list[str], element: str) -> bool:
            for word in words:
                if not word.lower() in os.path.basename(element).lower():
                    return False
            return True

        splitquery = shlex.split(query)
        return [element for element in data if contains_all_words(splitquery, element)]

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        raise NotImplementedError

    def add_to_config(self, config: dict[str, Any]) -> None:
        pass


available_sources: dict[str, Type[Source]] = {}
