from __future__ import annotations
import shlex
import asyncio
from typing import Tuple, Optional, Type, Any
import os.path
from collections import defaultdict
from dataclasses import dataclass, field
import logging
from traceback import print_exc

from ..entry import Entry
from ..result import Result

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class DLFilesEntry:
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    video: str = ""
    audio: Optional[str] = None
    buffering: bool = False
    complete: bool = False
    failed: bool = False
    buffer_task: Optional[asyncio.Task[Tuple[str, Optional[str]]]] = None


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

        mpv_process = asyncio.create_subprocess_exec(
            "mpv",
            *args,
            stdout=asyncio.subprocess.PIPE,
        )
        return await mpv_process

    async def get_entry(self, performer: str, ident: str) -> Entry:
        raise NotImplementedError

    async def search(self, query: str) -> list[Result]:
        raise NotImplementedError

    async def doBuffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        raise NotImplementedError

    async def buffer(self, entry: Entry) -> None:
        async with self.masterlock:
            if self.downloaded_files[entry.id].buffering:
                return
            self.downloaded_files[entry.id].buffering = True

        try:
            buffer_task = asyncio.create_task(self.doBuffer(entry))
            self.downloaded_files[entry.id].buffer_task = buffer_task
            video, audio = await buffer_task

            self.downloaded_files[entry.id].video = video
            self.downloaded_files[entry.id].audio = audio
            self.downloaded_files[entry.id].complete = True
        except Exception:
            print_exc()
            logger.error("Buffering failed for %s", entry)
            self.downloaded_files[entry.id].failed = True

        self.downloaded_files[entry.id].ready.set()

    async def play(self, entry: Entry) -> None:
        await self.ensure_playable(entry)

        if self.downloaded_files[entry.id].failed:
            del self.downloaded_files[entry.id]
            return

        if entry.skip:
            del self.downloaded_files[entry.id]
            return

        self.player = await self.play_mpv(
            self.downloaded_files[entry.id].video,
            self.downloaded_files[entry.id].audio,
            *self.extra_mpv_arguments,
        )
        await self.player.wait()
        self.player = None

    async def skip_current(self, entry: Entry) -> None:
        entry.skip = True
        self.downloaded_files[entry.id].buffering = False
        buffer_task = self.downloaded_files[entry.id].buffer_task
        if buffer_task is not None:
            buffer_task.cancel()
        self.downloaded_files[entry.id].ready.set()

        if (
            self.player is not None
        ):  # A race condition can occur here. In that case, just press the skip button again
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
